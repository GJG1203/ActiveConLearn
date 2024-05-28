import time

SOLVER = "ortools"

from cpmpy import *
from cpmpy.transformations.get_variables import get_variables
from utils import *
import math
from ortools.sat.python import cp_model as ort
from sklearn.preprocessing import MinMaxScaler

from utils import find_suitable_vars_subset2, find_optimal_vars_subset

from ConAcq import ConAcq
from utils import construct_bias, get_kappa



class RobustAcq(ConAcq):
    def __init__(self, gamma, grid, ct, bias, X, C_l, stopping_t=1, constraint_t=10, qg="pqgen", gqg= False, gfs=False, gfc=False, obj="proba", classifier=None,
                 classifier_name=None, time_limit=None, findscope_version=4, findc_version=1, tqgen_t=None,
                 qgen_blimit=5000):
        super().__init__(stopping_t, constraint_t, gamma, grid, ct, bias, X, C_l, qg, gqg, gfs, gfc, obj, classifier, classifier_name, time_limit, findscope_version,
                    findc_version, tqgen_t, qgen_blimit)

    
    def learn(self):
        
        # threshold to put constraints back into B when they are in Br
        probability_threshold = 0.8
        
        answer = True
        if len(self.B) == 0:
            self.B = construct_bias(self.X, self.gamma)
            
        helpThresh = 0

        while True:
            
            # add threshold1 and check if threshold is breached => break
            if helpThresh >= self.stoppingThresh:
                break
            
            # check if C_l is bigger than threshold2 and if so, retrain classifier and rearrange B and Br
            if self.constraintThresh >= len(self.C_l.constraints):
                self.train_classifier()
                self.rearrange_biases(probability_threshold)
            
            if self.debug_mode:
                print("Size of CL: ", len(self.C_l.constraints))
                print("Size of B: ", len(self.B))
                print("n of Queries: ", self.queries_count)

            gen_start = time.time()

            gen_flag, Y = self.call_query_generation(answer)

            gen_end = time.time()

            if not gen_flag:
                # if no query can be generated we need to check if we can generate a query with Br
                
                gen_flag2, Y2 = self.call_query_generation(constraint_set=self.Br)
                answer2 = self.ask_query(Y2)
                
                if answer2:
                    self.increase_stopping_threshold()
                
                else:
                    kappaBr = get_kappa(self.Br, Y)
                    scope2 = self.call_findscope(Y, kappaBr)
                    self.call_findc(scope2)               
                

            self.metrics.increase_generation_time(gen_end - gen_start)
            self.metrics.increase_generated_queries()
            self.metrics.increase_top_queries()
            kappaB = get_kappa(self.B, Y)

            answer = self.ask_query(Y)
            if answer:
                # it is a solution, so all candidates violated must go
                # B <- B \setminus K_B(e)
                #        print("Removing the following constraints 1:", [c for c in B if check_value(c) is not False] )
                self.remove_from_bias(kappaB)
                if self.debug_mode:
                    print("B:", len(self.B))

            else:  # user says UNSAT
                scope = self.call_findscope(Y, kappaB)
                self.call_findc(scope)
                
    def increase_stopping_threshold(self):
        self.stoppingThresh += 1
                
    def rearrange_biases(self, probability_threshold):
        data_pred = [self.get_con_features(c) for c in self.Br]
        myscore = self.classifier.predict_proba(data_pred)
        myscore = [m if len(m) > 1 else [0, m[0]] for m in myscore]

        P_c = [myscore[i][1] for i in range(len(myscore))]

        # Separate constraints into those to keep and those to put back in B
        wrongly_removed = []

        for i, c in enumerate(self.Br):
            if P_c[i] >= probability_threshold:
                wrongly_removed.append(c)
         
        # put the wrongly removed constraints back in B       
        for c in wrongly_removed:
            self.from_Br_to_B(c)

            
    def from_B_to_Br(self, c):

        # remove from B
        prev_B_length = len(self.B)
        self.B = list(set(self.B) - set(c))
        
        # add to Br
        prev_Br_length = len(self.Br)
        self.Br = list(set(self.Br) + set(c))

        # checks
        if not (prev_B_length - 1 == len(self.B)):
            raise Exception(f'constraint was not removed properly')
        
        if not (prev_Br_length + 1 == len(self.Br)):
            raise Exception(f'constraint was not added properly')
        
        
    def from_Br_to_B(self, c):

        # remove from Br
        prev_Br_length = len(self.Br)
        self.Br = list(set(self.Br) - set(c))
        
        # add to B
        prev_B_length = len(self.B)
        self.B = list(set(self.B) + set(c))

        # checks
        if not (prev_Br_length - 1 == len(self.Br)):
            raise Exception(f'constraint was not removed properly')
        
        if not (prev_B_length + 1 == len(self.B)):
            raise Exception(f'constraint was not added properly')