# -*- coding: utf-8 -*-

"""Main execution

This program searches for models that fit a specific motif.

"""

import time
import random
import copy
import json
import os
# import cProfile
# import pstats
# import io
import numpy as np
import matplotlib.pyplot as plt
from objects.organism_factory import OrganismFactory
from Bio import SeqIO

"""
Variable definition
"""
POPULATION_LENGTH = 0
DATASET_BASE_PATH_DIR = ""
RESULT_BASE_PATH_DIR = ""
POSITIVE_FILENAME = ""
NEGATIVE_FILENAME = ""
POPULATION_ORIGIN = ""
POPULATION_FILL_TYPE = ""
INPUT_FILENAME = ""
OUTPUT_FILENAME = ""
MAX_SEQUENCES_TO_FIT_POS = 0
MAX_SEQUENCES_TO_FIT_NEG = 0
MIN_ITERATIONS = 0
MIN_FITNESS = 0
RECOMBINATION_PROBABILITY = 0.0
THRESHOLD = 0.0
JSON_CONFIG_FILENAME = "config.json"
"""
Configuration of the object types
Populated by JSON read.
"""
configOrganism: dict = {}
configOrganismFactory: dict = {}
configConnector: dict = {}
configPssm: dict = {}
configShape: dict = {}


# list that holds the population
organism_population: list = []

# mean_nodes are the average number of nodes per organism in the population
# used to calculate organism complexity
mean_nodes: float = 0
# mean_fitness is the average fitness per organism in the population
# used to calculate organism complexity
mean_fitness: float = 0

# Initialize datasets
positive_dataset: list = []
negative_dataset: list = []


def main():
    """
    Main function for the motif seek
    """
    
    if i_am_main_process():  # XXX
        print("Loading parameters...")
    
    # Read positive set from specified file
    positive_dataset = read_fasta_file(DATASET_BASE_PATH_DIR + POSITIVE_FILENAME)
    
    # XXX
    if NEGATIVE_FILENAME is not None:
        # Read negative set from specified file
        negative_dataset = read_fasta_file(DATASET_BASE_PATH_DIR + NEGATIVE_FILENAME)
    else:
        # If no file was specified for negative set, it's generated from positive set
        if i_am_main_process():
            print("Generateing negative set...")
            negative_dataset = generate_negative_set(positive_dataset)
        else:
            negative_dataset = None  # this will only happen in parallel runs
        if RUN_MODE == 'parallel':
            # make sure all processes share the same negative set (the one of process 0)
            negative_dataset = comm.bcast(negative_dataset, root=0)

    mean_nodes = 0
    mean_fitness = 0
    
    if i_am_main_process():  # XXX
        print("Instantiating population...")
    
    """
    Generate initial population
    """
    # Instantiate organism Factory object with object configurations
    organism_factory = OrganismFactory(
        configOrganism, configOrganismFactory, configConnector, configPssm, rank, configShape
    )
    
    # Initialize the population of organisms
    if i_am_main_process():  # XXX
        
        # Initialize list
        organism_population = []
        
        # Generate population depending on origin and fill type.
        # Origin can be "random" or "file"(read a set of organisms from a file).
        if POPULATION_ORIGIN.lower() == "random":
            # For a random origin, we can generate #POPULATION_LENGTH organisms.
            for i in range(POPULATION_LENGTH):
                new_organism = organism_factory.get_organism()
                organism_population.append(new_organism)
        elif POPULATION_ORIGIN.lower() == "file":
            #if the population is seeded from file
            # Set the file organisms and fill with random/same organisms
            # POPULATION_LENGTH must be >= len(fileOrganisms)
            file_organisms = organism_factory.import_organisms(INPUT_FILENAME)
            remaining_organisms = POPULATION_LENGTH - len(file_organisms)
            fill_organism_population = []
    
            if POPULATION_FILL_TYPE.lower() == "random":
                # FILL remainder of the population WITH RANDOM organisms
                for i in range(remaining_organisms):
                    new_organism = organism_factory.get_organism()
                    fill_organism_population.append(new_organism)
    
            elif POPULATION_FILL_TYPE.lower() == "uniform":
                # FILL the remainder of the population WITH ORGANISMS IN FILE
                for i in range(remaining_organisms):
                    new_organism = copy.deepcopy(
                        file_organisms[i % len(file_organisms)]
                    )
                    fill_organism_population.append(new_organism)
                    new_organism.set_id(organism_factory.get_id())
            
            # join 
            organism_population = file_organisms + fill_organism_population
    
        else:
            raise Exception("Not a valid population origin, "
                + "check the configuration file.")
        
        print("Population size =", len(organism_population))
    
    else:
        organism_population = None
    
    
    """
    Initialize iteration variables.
    """
    iterations = 0
    max_score = float("-inf")
    last_max_score = 0.0
    # Organism with highest fitness in the simulation
    best_organism = (
        None,  # the organism object
        -np.inf,  # its fitness
        0  # number of nodes it is made of
    )
    # Organism with highest fitness in the iteration
    max_organism = (
        None,  # the organism object
        -np.inf,  # its fitness
        0  # number of nodes it is made of
    )
    timeformat = "%Y-%m-%d--%H-%M-%S"
    
    if i_am_main_process():  # XXX
        print("Starting execution...")

    # Main loop, it iterates until organisms do not get a significant change
    # or MIN_ITERATIONS or MIN_FITNESS is reached.

    while not is_finished(END_WHILE_METHOD, iterations, max_score, 
                          last_max_score):
        
        # XXX
        if i_am_main_process():
            # Shuffle population
            # Organisms are shuffled for deterministic crowding selection
            random.shuffle(organism_population)        
        
        # XXX
        if RUN_MODE == 'parallel':
            # FRAGMENT AND SCATTER THE POPULATION
            organism_population = fragment_population(organism_population)
            organism_population = comm.scatter(organism_population, root=0)
            
            # print to check that the sub-populations are correct
            # my_ids = [org._id for org in organism_population]
            # print("From process " + str(rank) + ": loc pop is " + str(my_ids))
        
        # XXX
        # Shuffle datasets (if required)
        if RANDOM_SHUFFLE_SAMPLING_POS:
            positive_dataset = shuffle_dataset(positive_dataset)
        if RANDOM_SHUFFLE_SAMPLING_NEG:
            negative_dataset = shuffle_dataset(negative_dataset)
        
        # Reset max_score
        last_max_score = max_score
        max_score = float("-inf")
        changed_best_score = False
        initial = time.time()
        
        a_fitness = []
        a_nodes = []
        
        # Deterministic crowding
        # Iterate over pairs of organisms
        for i in range(0, len(organism_population) - 1, 2):
            org1 = organism_population[i]
            org2 = organism_population[i + 1]
            
            pos_set_sample = random.sample(positive_dataset, 3)  # !!! Temporarily hardcoded number of sequences
            ref_seq = pos_set_sample[0]
            
            # Decide whether the parents are going to be recombined or mutated
            if random.random() < organism_factory.recombination_probability:
                # Recombination case; no mutation
                child1, child2 = organism_factory.get_children(
                    org1, org2, ref_seq, pos_set_sample
                )
            
            else:
                # Non-recomination case; the children get mutated
                child1, child2 = organism_factory.clone_parents(org1, org2)
                # Mutate the children: the children in this non-recombination
                # case are just a mutated versions of the parents
                child1.mutate(organism_factory)
                child2.mutate(organism_factory)
            
            # Make two pairs: each parent is paired with the more similar child
            # (the child with higher ratio of nodes from that parent).
            pair_children = []
            ''' pair_children is a list of two elements. The two parents we are
            now working with are elements i and i+1 in  organism_population.
            We need to pair each of them with one of the two children obtained
            with  get_children  method.
            
                - The first element in  pair_children  will be a tuple where
                  the first element is organism i, and the second one is a
                  child
                  
                - The second element in  pair_children  will be a tuple where
                  the first element is organism i+1, and the second one is the
                  other child
            '''
            
            # get parent1/parent2 ratio for the children
            child1_p1p2_ratio = child1.get_parent1_parent2_ratio()
            child2_p1p2_ratio = child2.get_parent1_parent2_ratio()
            
            # If a parent gets paired with an empty child, the empty child is
            # substituted by a deepcopy of the parent, i.e. the parent escapes
            # competition
            if child1_p1p2_ratio > child2_p1p2_ratio:
                # org1 with child1
                if child1.count_nodes() > 0:
                    pair_children.append( (org1, child1) )
                else:
                    pair_children.append( (org1, copy.deepcopy(org1)) )
                # org2 with child2
                if child2.count_nodes() > 0:
                    pair_children.append( (org2, child2) )
                else:
                    pair_children.append( (org2, copy.deepcopy(org2)) )
            else:
                # org1 with child2
                if child2.count_nodes() > 0:
                    pair_children.append( (org1, child2) )
                else:
                    pair_children.append( (org1, copy.deepcopy(org1)) )
                # org2 with child1
                if child1.count_nodes() > 0:
                    pair_children.append( (org2, child1) )
                else:
                    pair_children.append( (org2, copy.deepcopy(org2)) )
            
            # Make the two organisms in each pair compete
            # j index is used to re insert winning organism into the population
            for j in range(len(pair_children)):
                '''
                when j is 0 we are dealing with organism i
                when j is 1 we are dealing with organism i+1
                
                Therefore, the winner of the competition will replace element
                i+j in  organism_population
                '''

                first_organism = pair_children[j][0]  # Parent Organism
                second_organism = pair_children[j][1]  # Child Organism
                
                # Boltzmannian fitness
                if FITNESS_FUNCTION == "boltzmannian":
                    performance1 = first_organism.get_boltz_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS],
                                                                    negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG],
                                                                    GENOME_LENGTH)
                    fitness1 = performance1["score"]
                    
                    performance2 = second_organism.get_boltz_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS],
                                                                     negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG],
                                                                     GENOME_LENGTH)
                    fitness2 = performance2["score"]
                    
                    fitness1 = round(fitness1, 8)
                    fitness2 = round(fitness2, 8)
                
                # Kolmogorov fitness
                # Computes Kolmogorov-Smirnov test on positive/negative set scores
                elif FITNESS_FUNCTION == "kolmogorov":
                    performance1 = first_organism.get_kolmogorov_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS],
                                                                    negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])
                    fitness1 = performance1["score"]
                    
                    performance2 = second_organism.get_kolmogorov_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS],
                                                                    negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])

                    fitness2 = performance2["score"]
                    
                    fitness1 = round(fitness1, 8)
                    fitness2 = round(fitness2, 8)

                # Discriminative fitness
                elif FITNESS_FUNCTION == "discriminative":
                    positive_performance1 = first_organism.get_additive_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS])
                    negative_performance1 = first_organism.get_additive_fitness(negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])
                    p_1 = positive_performance1["score"]
                    n_1 = negative_performance1["score"]
                    fitness1 =  p_1 - n_1
                    
                    positive_performance2 = second_organism.get_additive_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS])
                    negative_performance2 = second_organism.get_additive_fitness(negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])
                    p_2 = positive_performance2["score"]
                    n_2 = negative_performance2["score"]
                    fitness2 =  p_2 - n_2
                
                elif FITNESS_FUNCTION == "welchs":
                    # First organism
                    positive_performance1 = first_organism.get_additive_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS])
                    negative_performance1 = first_organism.get_additive_fitness(negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])
                    p_1 = positive_performance1["score"]
                    n_1 = negative_performance1["score"]
                    
                    # Standard deviations
                    sigma_p_1 = positive_performance1["stdev"]
                    sigma_n_1 = negative_performance1["stdev"]
                    
                    # Lower bound to sigma
                    # (Being more consistent than that on the sets will not help
                    # your fitness)
                    if sigma_p_1 < 1:
                        sigma_p_1 = 1
                    if sigma_n_1 < 1:
                        sigma_n_1 = 1
                    
                    # Standard errors
                    sterr_p_1 = sigma_p_1 / MAX_SEQUENCES_TO_FIT_POS**(1/2)
                    sterr_n_1 = sigma_n_1 / MAX_SEQUENCES_TO_FIT_NEG**(1/2)
                    
                    # Welch's t score
                    fitness1 =  (p_1 - n_1) / (sterr_p_1**2 + sterr_n_1**2)**(1/2)
                    
                    # Second organism
                    positive_performance2 = second_organism.get_additive_fitness(positive_dataset[:MAX_SEQUENCES_TO_FIT_POS])
                    negative_performance2 = second_organism.get_additive_fitness(negative_dataset[:MAX_SEQUENCES_TO_FIT_NEG])
                    p_2 = positive_performance2["score"]
                    n_2 = negative_performance2["score"]
                    
                    # Standard deviations
                    sigma_p_2 = positive_performance2["stdev"]
                    sigma_n_2 = negative_performance2["stdev"]
                    
                    # Lower bound to sigma
                    # (Being more consistent than that on the sets will not help
                    # your fitness)
                    if sigma_p_2 < 1:
                        sigma_p_2 = 1
                    if sigma_n_2 < 1:
                        sigma_n_2 = 1
                    
                    # Standard errors
                    sterr_p_2 = sigma_p_2 / MAX_SEQUENCES_TO_FIT_POS**(1/2)
                    sterr_n_2 = sigma_n_2 / MAX_SEQUENCES_TO_FIT_NEG**(1/2)
                    
                    # Welch's t score
                    fitness2 =  (p_2 - n_2) / (sterr_p_2**2 + sterr_n_2**2)**(1/2)
                                    
                else:
                    raise Exception("Not a valid fitness function name, "
                                    + "check the configuration file.")
                
                if MAX_NODES != None:  # Upper_bound to complexity
                    
                    if first_organism.count_nodes() > MAX_NODES:
                        fitness1 = -1000 * int(first_organism.count_nodes())
                    
                    if second_organism.count_nodes() > MAX_NODES:
                        fitness2 = -1000 * int(second_organism.count_nodes())

                if MIN_NODES != None:  # Lower_bound to complexity
                    
                    if first_organism.count_nodes() < MIN_NODES:
                        fitness1 = -1000 * int(first_organism.count_nodes())
                    
                    if second_organism.count_nodes() < MIN_NODES:
                        fitness2 = -1000 * int(second_organism.count_nodes())
                
                
                # Competition
                if fitness1 > fitness2:  # The first organism wins (the parent wins)
                    # Set it back to the population and save fitness
                    # for next iteration
                    organism_population[i + j] = first_organism
                    a_fitness.append(fitness1)
                    # If the parent wins, mean_nodes don't change
                    a_nodes.append(first_organism.count_nodes())

                    # Check if its the max score in that iteration
                    if fitness1 > max_score:
                        max_score = fitness1
                        max_organism = (
                            first_organism,
                            fitness1,
                            first_organism.count_nodes()
                        )

                    # Check if its the max score so far and if it is set it as
                    # best organism
                    if max_organism[1] > best_organism[1]:
                        # ID, EF, Nodes, Penalty applied
                        best_organism = max_organism
                        changed_best_score = True

                else:  # The second organism wins (the child wins)
                    # Set it back to the population and save fitness for next
                    # iteration
                    organism_population[i + j] = second_organism
                    a_fitness.append(fitness2)
                    # If the child wins, update mean_nodes
                    # mean_nodes = ((meanNodes * POPULATION_LENGTH) +
                    # second_organism.count_nodes() -
                    # first_organism.count_nodes()) / POPULATION_LENGTH
                    a_nodes.append(second_organism.count_nodes())

                    # Check if its the max score in that iteration
                    if fitness2 > max_score:
                        max_score = fitness2
                        max_organism = (
                            second_organism,
                            fitness2,
                            second_organism.count_nodes()
                        )

                    # Check if its the max score so far and if it is set it as
                    # best organism
                    if fitness2 > best_organism[1]:
                        # ID, EF, Nodes, Penalty applied
                        best_organism = max_organism
                        changed_best_score = True

                # END FOR j

            # END FOR i
        
        if RUN_MODE == 'parallel':  # XXX
            # GATHER AND FLATTEN THE POPULATION
            organism_population = comm.gather(organism_population, root=0)
            organism_population = flatten_population(organism_population)
            
            # print to check that the population is correct
            # This is just for code testing/debugging
            # if rank == 0:
            #     my_ids = [org._id for org in organism_population]
            #     print("From process " + str(rank) + ": gathered pop is " + str(my_ids))
            
            # Also gather a_fitness and a_nodes
            a_fitness = comm.gather(a_fitness, root=0)
            a_fitness = flatten_population(a_fitness)
            a_nodes   = comm.gather(a_nodes,   root=0)
            a_nodes   = flatten_population(a_nodes)
        
        if i_am_main_process():
            # Mean fitness in the population
            mean_fitness = np.mean(a_fitness)
            # Standard deviation of fitness in the population
            standard_dev_fitness = np.std(a_fitness)
            # Inequality of fitness in the population (measured with the Gini coefficient)
            gini_fitness = gini_RSV(a_fitness)
            # Mean number of nodes per organism in the population
            mean_nodes = np.mean(a_nodes)
            
            # Show IDs of final array
            # print("-"*10)
            _m, _s = divmod((time.time() - initial), 60)
            _h, _m = divmod(_m, 60)
            s_time = "{}h:{}m:{:.2f}s".format(int(_h), int(_m), _s)
            print_ln(
                (
                    "Iter: {} AF:{:.2f} SDF:{:.2f} GF:{:.2f} AN:{:.2f}"
                    + " - MO: {} MF: {:.2f} MN: {}"
                    + " -  BO: {} BF: {:.2f} BN: {} Time: {}"
                ).format(
                    iterations,  # "Iter"
                    mean_fitness,  # "AF"
                    standard_dev_fitness,  # "SDF"
                    gini_fitness,  # "GF"
                    mean_nodes,  # "AN"
                    max_organism[0]._id,  # "MO"
                    max_organism[1],  # "MF" (fitness)
                    max_organism[2],  # "MN" (nodes)
                    best_organism[0]._id,  # "BO"
                    best_organism[1],  # "BF" (fitness)
                    best_organism[2],  # "BN" (nodes)
                    s_time,  # Time
                ),
                RESULT_BASE_PATH_DIR + OUTPUT_FILENAME,
            )
            
            # Print against a random positive sequence
            pos_seq_index = random.randint(0, len(positive_dataset)-1)
            placement = max_organism[0].get_placement(positive_dataset[pos_seq_index])
            placement.print_placement(stdout = True)
            
            
            # XXX
            if RANDOM_SHUFFLE_SAMPLING_POS:
                # If the dataset is shuffled, prepare a sorted version for the
                # 'export' functions, so that regardless of the current status of
                # the dataset, the sequences exported are always the same and
                # always appear in the same order.
                pos_set_for_export = sorted(positive_dataset)
            else:
                pos_set_for_export = positive_dataset
            
            
            # Export organism if new best organism
            if changed_best_score:
                filename = "{}_{}".format(
                    time.strftime(timeformat), best_organism[0]._id
                )
                export_organism(
                    best_organism[0], pos_set_for_export, filename, organism_factory
                )
            # Periodic organism export
            if iterations % PERIODIC_ORG_EXPORT == 0:
                filename = "{}_{}".format(
                    time.strftime(timeformat), max_organism[0]._id
                )
                export_organism(
                    max_organism[0], pos_set_for_export, filename, organism_factory
                )
            
            # Periodic population export
            if iterations % PERIODIC_POP_EXPORT == 0:
                # Select a random positive DNA sequence to use for the population export
                seq_idx = random.randint(0, len(pos_set_for_export)-1)
                
                export_population(
                    organism_population, pos_set_for_export, organism_factory,
                    iterations, seq_idx
                )
                
                # Export plot, too
                export_plots()
        
        iterations += 1
        # END WHILE


def shuffle_dataset(dataset: list) -> list:
    '''
    Returns the dataset (list of DNA sequences) in random order. Instead of
    directly shuffling the list, the indexes are shuffled. This is done to
    minimize the amount of MPI communication when the program is run in
    parallel mode. Indeed, we want all the processes to compute fitness on the
    same subset, defined as dataset[:MAX_SEQUENCES_TO_FIT_***]. So we want the
    processes to share the same random permutation of the datset. This function
    ensures that by MPI broadcasting the indexes that define the permutation,
    instead of broadcasting the shuffled dataset of sequences.
    '''
    indexes = list(range(len(dataset)))
    random.shuffle(indexes)
    if RUN_MODE == 'parallel':
        # In parallel runs, the order is the one generated by process 0
        indexes = comm.bcast(indexes, root=0)
    # Sort dataset according to indexes
    return [dataset[i] for i in indexes]


def get_all_kmers(seq: str, kmer_len: int) -> list:
    ''' Returns the list of all the k-mers of length k in seq. '''
    return [seq[i:i+kmer_len] for i in range(len(seq)-kmer_len+1)]


def get_k_sampled_sequence(seq: str, kmer_len: int) -> str:
    '''
    All kmers are stored. Than sampled without replacement.
    Example with k = 3:
    ATCAAAGTCCCCGTACG
    for which 3-mers are
    ATC, TCA, CAA, AAA, AAG, ...
    A new sequence is generated by sampling (without replacement) from that
    complete set of k-mers.
    The nucleotide content (1-mers content) may not be perfectly identical
    because of overlap between k-mers that are then randomly sampled.
    The length of the sequence is preserved.
    '''
    
    if kmer_len > 1:
        n_kmers = len(seq) // kmer_len
        n_nuclotides_rem = len(seq) % kmer_len
        
        all_kmers = get_all_kmers(seq, kmer_len)
        sampled_seq_list = random.sample(all_kmers, n_kmers)
        n_nucleotides = random.sample(seq, n_nuclotides_rem)
        sampled_seq_list += n_nucleotides
    
    else:
        sampled_seq_list = random.sample(seq, len(seq))
    
    return "".join(sampled_seq_list)


def generate_negative_set(positive_set: list) -> list:
    ''' Generates a negative set made of pseudosequences that resemble the
    positive set in terms of k-mer frequencies. If the size of the negative set
    is not specified, it will be the size of the positive set. If the size is
    specified and it's k*len(positive_set) where k is an integer, every sequence
    in the positive set contributes to exactly k sequences in the negative set.
    If the required size is not a multiple of len(positive_set), the remaining
    number of sequences (as many as the remainder of the division) are selected
    randomly from the positive set. '''
    
    if GENERATED_NEG_SET_SIZE is None:
        neg_set_size = len(positive_set)
    else:
        neg_set_size = GENERATED_NEG_SET_SIZE
    q = neg_set_size // len(positive_set)
    r = neg_set_size % len(positive_set)
    negative_set = []
    for i in range(q):
        for seq in positive_set:
            negative_set.append(get_k_sampled_sequence(seq, GENERATED_NEG_SET_KMER_LEN))
    for seq in random.sample(positive_set, r):
        negative_set.append(get_k_sampled_sequence(seq, GENERATED_NEG_SET_KMER_LEN))
    return negative_set


def is_finished(
        method: str, iterations: int, max_score: float, last_max_score: float
) -> bool:
    """Checks if main while loop is finished
    methods: 'Iterations', 'minScore', 'Threshold'

    Args:
        method: Name of the finishing method
        max_score: max score recorded on the current iteration
        last_max_score: max score recorded on the laset iteration
        iterations: Number of the current iteration

    Returns:
        True if program should finnish.
        False otherwise
    """

    if method.lower() == "iterations":
        return iterations >= MIN_ITERATIONS

    if method.lower() == "fitness":
        return max_score >= MIN_FITNESS

    if method.lower() == "threshold":
        return abs(last_max_score - max_score) <= THRESHOLD

    return True


def export_organism(
        organism, dataset: list, filename: str, factory: OrganismFactory
) -> None:
    """Exports a single organism in json format, visual format and its
    recognizers binding

    Args:
        organism (OrganismObject): organism to export
        dataset: Sequences to check the organism binding
        filename: Previous info to export filenames. Common in all filenames
        factory: Used to export in json format
    """

    organism_file = "{}{}_organism.txt".format(RESULT_BASE_PATH_DIR, filename)
    organism_file_json = "{}{}_organism.json".format(
        RESULT_BASE_PATH_DIR, filename
    )
    results_file = "{}{}_results.txt".format(RESULT_BASE_PATH_DIR, filename)

    organism.export(organism_file)
    organism.export_results(dataset, results_file)
    factory.export_organisms([organism], organism_file_json)


def export_population(
        population, dataset: list, factory: OrganismFactory,
        generation: int, dna_seq_idx: int
) -> None:
    """Exports a single organism in json format, visual format and its
    recognizers binding

    Args:
        organism (OrganismObject): organism to export
        dataset: Sequences to check the organism binding
        filename: Previous info to export filenames. Common in all filenames
        factory: Used to export in json format
    """
    
    population_dir = RESULT_BASE_PATH_DIR + "population"
    
    population_name = "{}_generation_{}".format(
        time.strftime("%Y-%m-%d--%H-%M-%S"), generation
    )
    
    population_txt_file = os.path.join(
        population_dir, population_name + ".txt"
    )
    population_placements_file = os.path.join(
        population_dir, population_name + "_placements.txt"
    )
    population_json_file = os.path.join(
        population_dir, population_name + ".json"
    )
    
    for organism in population:
        # Compile the file with all the organisms of the population printed
        organism.export(population_txt_file)
        
        # Compile the file with all the organisms of the population placed
        # Write organism ID
        placements_file = open(population_placements_file, "a+")
        placements_file.write("***** Organism {} *****\t".format(organism._id))
        # Write who is parent 1
        placements_file.write("p1:")
        placements_file.write(str(organism.assembly_instructions['p1']))
        # Write who is parent 2
        placements_file.write(", p2:")
        placements_file.write(str(organism.assembly_instructions['p2']))
        placements_file.write("\n")
        placements_file.close()
        # Write organism placement on a single positive sequence
        organism.export_results([dataset[dna_seq_idx]], population_placements_file)
    
    # Make a file with all the organisms exported in json format
    factory.export_organisms(population, population_json_file)


def export_plots() -> None:
    """
    Exports:
        A plot showing the trend in the fitness of the maximum organism and the
        trend in the average fitness.
    
    Saved as png in the 'plots' subfolder in the simulation directory.
    """
    
    plots_dir = RESULT_BASE_PATH_DIR + "plots"
    
    # The stats are taken from the 'output.txt' file in the simulation directory
    output_file = RESULT_BASE_PATH_DIR + 'output.txt'
    
    # Read the output.txt file
    f = open(output_file, 'r')
    lines = f.readlines()
    f.close()
    
    # Parse stats into lists
    AF_list = []
    MF_list = []
    GF_list = []
    for l in lines:
        AF = l.split('AF:')[1].split(' ')[0]
        AF_list.append(float(AF))
        MF = l.split('MF: ')[1].split(' ')[0]
        MF_list.append(float(MF))
        GF = l.split('GF:')[1].split(' ')[0]
        GF_list.append(float(GF))
    
    # Ignore negative values
    AF_trunc_list = [x if x>=0 else None for x in AF_list]
    MF_trunc_list = [x if x>=0 else None for x in MF_list]
    
    # Plot together AF and MF
    plt.plot(AF_trunc_list, label="Average fitness")
    plt.plot(MF_trunc_list, label="Fitness of max org")
    plt.legend()
    filepath = os.path.join(plots_dir, "AF-MF.png")
    plt.savefig(filepath)
    plt.close()


def i_am_main_process():
    ''' Returns True if rank is None (which happens when the run is serial) or
    when rank is 0 (which happens when the run is parallel and the program is
    executed by the process with rank 0). '''
    return not rank


def check_mpi_settings():
    ''' If the number of processes exceeds the number of pairs of organisms in
    the population, some processes will be left with an empty population. In
    that case, to avoid wasting computing power, an error is raised. '''
    if p > int(POPULATION_LENGTH / 2):
        raise ValueError("The minimum number of organisms assigned to each " +
                         "process is 2 (you need a pair for recombination events " +
                         "to take place). Thus, the maximum number of processes" +
                         "to be used is POPULATION_LENGTH / 2 (case in which " +
                         "each process works on one single pair of organisms). " +
                         "Please decrease number of processes to avoid wastes, " +
                         "i.e., processes being assigned an empty subpopulation, " +
                         "or increase the POPULATION_LENGTH.")


def check_dir(dir_path):
    ''' If the directory at the specified path doesn't exists, it's created.
    Any missing parent directory is also created. If the directory already
    exists, it is left un modified. This function works even when executed in
    parallel my several processes (makedir would crash if they try to make the
    directory at about the same time).
    '''
    os.makedirs(dir_path, exist_ok=True)


def set_up():
    """Reads configuration file and sets up all program variables

    """

    # specify as global variable so it can be accesed in local
    # contexts outside setUp

    global RUN_MODE  # XXX
    global END_WHILE_METHOD
    global POPULATION_LENGTH
    global DATASET_BASE_PATH_DIR
    global RESULT_BASE_PATH_DIR
    global POSITIVE_FILENAME
    global NEGATIVE_FILENAME
    global GENERATED_NEG_SET_SIZE  # XXX
    global GENERATED_NEG_SET_KMER_LEN  # XXX
    global RESULT_PATH_PATH_DIR
    global MAX_SEQUENCES_TO_FIT_POS
    global MAX_SEQUENCES_TO_FIT_NEG
    global RANDOM_SHUFFLE_SAMPLING_POS
    global RANDOM_SHUFFLE_SAMPLING_NEG
    global FITNESS_FUNCTION
    global GENOME_LENGTH
    global MIN_ITERATIONS
    global MIN_FITNESS
    global THRESHOLD
    global POPULATION_ORIGIN
    global POPULATION_FILL_TYPE
    global INPUT_FILENAME
    global OUTPUT_FILENAME
    global PERIODIC_ORG_EXPORT
    global PERIODIC_POP_EXPORT
    global MAX_NODES
    global MIN_NODES

    # Config data
    global configOrganism
    global configOrganismFactory
    global configConnector
    global configPssm
    global configShape
    
    # MPI variables  # XXX
    global comm
    global rank
    global p

    config = read_json_file(JSON_CONFIG_FILENAME)
    
    POPULATION_LENGTH = config["main"]["POPULATION_LENGTH"]
    if POPULATION_LENGTH % 2 != 0:
        raise Exception("POPULATION_LENGTH must be an even number.")
    
    RUN_MODE = config["main"]["RUN_MODE"]  # XXX
    if RUN_MODE == "parallel":
        from mpi4py import MPI  # mpi4py is only imported if needed
        comm = MPI.COMM_WORLD
        rank = comm.Get_rank()
        p = comm.Get_size()
        check_mpi_settings()
    elif RUN_MODE == "serial":
        comm, rank, p = None, None, None
    else:
        raise ValueError('RUN_MODE should be "serial" or "parallel".')
    
    
    DATASET_BASE_PATH_DIR = config["main"]["DATASET_BASE_PATH_DIR"]
    # XXX
    if i_am_main_process():
        print('\n==================\nRUN_MODE: {}\n==================\n'.format(
            RUN_MODE))  # Remind the user about the chosen RUN_MODE
        RESULT_BASE_PATH_DIR = (
            config["main"]["RESULT_BASE_PATH_DIR"]
            + time.strftime("%Y%m%d%H%M%S") + "/")
    POSITIVE_FILENAME = config["main"]["POSITIVE_FILENAME"]
    NEGATIVE_FILENAME = config["main"]["NEGATIVE_FILENAME"]
    GENERATED_NEG_SET_SIZE = config["main"]["GENERATED_NEG_SET_SIZE"]
    GENERATED_NEG_SET_KMER_LEN = config["main"]["GENERATED_NEG_SET_KMER_LEN"]
    MAX_SEQUENCES_TO_FIT_POS = config["main"]["MAX_SEQUENCES_TO_FIT_POS"]
    MAX_SEQUENCES_TO_FIT_NEG = config["main"]["MAX_SEQUENCES_TO_FIT_NEG"]
    RANDOM_SHUFFLE_SAMPLING_POS = config["main"]["RANDOM_SHUFFLE_SAMPLING_POS"]
    RANDOM_SHUFFLE_SAMPLING_NEG = config["main"]["RANDOM_SHUFFLE_SAMPLING_NEG"]
    FITNESS_FUNCTION = config["main"]["FITNESS_FUNCTION"]
    GENOME_LENGTH = config["main"]["GENOME_LENGTH"]
    MIN_ITERATIONS = config["main"]["MIN_ITERATIONS"]
    MIN_FITNESS = config["main"]["MIN_FITNESS"]
    THRESHOLD = config["main"]["THRESHOLD"]
    END_WHILE_METHOD = config["main"]["END_WHILE_METHOD"]
    POPULATION_ORIGIN = config["main"]["POPULATION_ORIGIN"]
    POPULATION_FILL_TYPE = config["main"]["POPULATION_FILL_TYPE"]
    INPUT_FILENAME = config["main"]["INPUT_FILENAME"]
    OUTPUT_FILENAME = config["main"]["OUTPUT_FILENAME"]
    PERIODIC_ORG_EXPORT = config["main"]["PERIODIC_ORG_EXPORT"]
    PERIODIC_POP_EXPORT = config["main"]["PERIODIC_POP_EXPORT"]
    MAX_NODES = config["organism"]["MAX_NODES"]
    MIN_NODES = config["organism"]["MIN_NODES"]

    # Create directory where the output and results will be stored
    if i_am_main_process():  # XXX
        check_dir(RESULT_BASE_PATH_DIR)
        check_dir(RESULT_BASE_PATH_DIR + "population")
        check_dir(RESULT_BASE_PATH_DIR + "plots")

    # Store Config into variables to use later
    configOrganism = config["organism"]
    configOrganismFactory = config["organismFactory"]
    configConnector = config["connector"]
    configPssm = config["pssm"]
    configShape = config["shape"]

    # Throw config on a file
    if i_am_main_process():  # XXX
        parameters_path = RESULT_BASE_PATH_DIR + "parameters.txt"
        print_ln("-" * 50, parameters_path)
        print_ln(" " * 20 + "PARAMETERS", parameters_path)
        print_ln("-" * 50, parameters_path)
    
        print_config_json(config["main"], "Main Config", parameters_path)
        print_config_json(configOrganism, "Organism Config", parameters_path)
        print_config_json(
            configOrganismFactory, "Organism Factory Config", parameters_path
        )
        print_config_json(configConnector, "Connector Config", parameters_path)
        print_config_json(configPssm, "PSSM Config", parameters_path)
        print_config_json(configShape, "Shape Config", parameters_path)
    
        print_ln("-" * 50, parameters_path)


def read_fasta_file(filename: str) -> list:
    """Reads a fasta file and returns an array of DNA sequences (strings)

    TODO: probably it can be useful to create our own Sequence object that
    creates the string and stores some properties from fasta format. Also
    we can adapt the current program to use Biopythons's Seq object.

    Args:
        filename: Name of the file that contains FASTA format sequences to read

    Returns:
        The set of sequences in string format

    """
    dataset = []

    fasta_sequences = SeqIO.parse(open(filename), "fasta")

    for fasta in fasta_sequences:
        dataset.append(str(fasta.seq).lower())

    return dataset


def read_json_file(filename: str) -> dict:
    """Reads a JSON file and returns a dictionary with the content

    Args:
        filename: Name of the json file to read

    Returns:
        Dictionary with the json file info

    """

    with open(filename) as json_content:

        return json.load(json_content)


def print_config_json(config: dict, name: str, path: str) -> None:
    """Print the config file on std out and send it to a file.
    It is useful so we can know which was the configuration on every run

    Args:
        config: Configuration file to print
        name: Title for the configuration file
        path: File to export the configuration info
    """
    print_ln("{}:".format(name), path)

    for key in config.keys():
        print_ln("{}: {}".format(key, config[key]), path)
    print_ln("\n", path)


def print_ln(string: str, name_file: str) -> None:
    """Shows the string on stdout and write it to a file
    (like the python's logging modules does)

    Args:
        string: Information to print on stdout and file
        name_file: path to the file to export the string
    """

    print(string)

    # Here we are sure file exists
    _f = open(name_file, "a+")
    _f.write(string + "\n")
    _f.close()


def gini_RSV(values_for_each_class):
    '''
    Gini coefficient, modified in order to be alble to deal with negative
    values as in "Inequality measures and the issue of negative incomes"
    (Raffinetti, Siletti, Vernizzi)

    Parameters
    ----------
    values_for_each_class : array-like object
        Values associated to each class.
        They don't need to be already sorted and/or normalized.
        They can also be negative.

    Returns
    -------
    giniRSV : float
        Ranges from 0 (perfect equality) to 1 (maximal inequality).

    '''
    
    N = len(values_for_each_class)
    
    numerator = 0
    for i in values_for_each_class:
        for j in values_for_each_class:
            numerator += abs(i - j)
    
    pos = 0  # sum over the positive values
    neg = 0  # sum over the negative values (in absolute value)
    for x in values_for_each_class:
        if x >= 0:
            pos += x
        else:
            neg += -x
    
    mu_RSV = (N - 1) * (pos + neg) / N**2  # modified mu parameter
    
    if mu_RSV == 0:
        # Manage two special cases (avoiding 0-division error):
        #   - when a single value is the input
        #   - when all the values in the input are 0
        # In both cases mu_RSV will be 0
        # No inequality is measurable, and therefore 0 is returned
        return 0
    denominator = 2 * N**2 * mu_RSV
    giniRSV = numerator / denominator
    
    return giniRSV


def fragment_population(population):
    '''
    This function is used when running the pipeline in parallel mode via MPI.
    It takes as input a list of organisms ('population') and turns it into a
    list of lists, where each element is the sublist of organisms assigned to
    one of the processes.
    
    E.g.: if the number of processes is 3, and the population is made of 10
    organisms we have
        input population:
            [org0, org1, org2, org3, org4, org5, org6, org7, org8, org9]
        number of pairs:
            5
        most even distribution of pairs over 3 processes:
            [2, 2, 1]
        output population:
            [[org0, org1, org2, org3], [org4, org5, org6, org7], [org8, org9]]
    '''
    
    # Avoid errors if the function is called on all processes during a parallel
    # run. With the following code we don't have to worry about calling the
    # fragment_population_function only on the "main" process.
    if population is None:
        return None
    
    # Number of pairs of organisms
    n_pairs = int(len(population) / 2)
    q = n_pairs // p  # p is the number of processes
    r = n_pairs % p  # p is the number of processes
    # Number of pairs of organisms assigned to each process
    local_n_pairs_list = [q + 1] * r + [q] * (p - r)
    # Number of organisms assigned to each process
    sendcounts = [n*2 for n in local_n_pairs_list]
    # Make a list where each element is the list of organism for a process
    it = iter(population)
    population = [[next(it) for _ in range(size)] for size in sendcounts]
    # Now the population list is "fragmented" (list -> list of lists)
    return population


def flatten_population(population):
    '''
    This function is used when running the pipeline in parallel mode via MPI.
    It is the reverse function of the 'fragment_population' function.
    It takes as input a "fragmented" population (list of lists) and returns
    the entire population as a simple list of organisms (list).
    '''
    
    # Avoid errors if the function is called on all processes during a parallel
    # run. With the following code we don't have to worry about calling the
    # flatten_population only on the "main" process.
    if population is None:
        return None
    
    flat_population = []
    for sublist in population:
        for item in sublist:
            flat_population.append(item)
    return flat_population

if __name__ == "__main__":
    
    # Reads configuration file and sets up all program variables
    set_up()
    
    if i_am_main_process():
        INITIAL = time.time()
    
    # Profiling
    # PROFILER = cProfile.Profile()
    # PROFILER.enable()
    
    # Main function
    main()
    
    # Profiler output
    # PROFILER.disable()
    # STRING = io.StringIO()
    # SORTBY = "cumulative"
    # PS = pstats.Stats(PROFILER, stream=STRING).sort_stats(SORTBY)
    # PS.print_stats()
    # print(STRING.getvalue())
    
    # Print final execution time and read parameters
    if i_am_main_process():
        _M, _S = divmod((time.time() - INITIAL), 60)
        _H, _M = divmod(_M, 60)
        print_ln(
            "Time: {}h:{}m:{:.2f}s".format(int(_H), int(_M), _S),
            RESULT_BASE_PATH_DIR + "parameters.txt")
    
    



