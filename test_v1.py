#%%
import os
from os.path import join
import numpy as np
import torch
import json
import random
import math
from tqdm import tqdm
from transformers import AutoTokenizer
from transformers import AutoModelForCausalLM
seedn=42
# random.seed(seedn)
from utils.data import *
from utils.metrics import *
device = 'cuda'
file_name = os.path.basename(__file__)
print("File Name:", file_name)

from huggingface_hub import login
from env_config import *
login(hf_api_key_w, add_to_git_credential=True)

# import wandb
# os.environ["WANDB_PROJECT"] = "syn_method" # name your W&B project 

#%%
random.seed(seedn)
sample_ratio = 1
data_path = '/home/rokabe/data2/cava/data/solid-state_dataset_2019-06-27_upd.json'  # path to the inorganic crystal synthesis data (json)
# data_path = '/home/rokabe/data2/cava/data/solutionsynthesis_dataset_202185.json'    # path to the solution based synthesis data (json)
data = json.load(open(data_path, 'r'))
num_sample = int(len(data)*sample_ratio)
separator=' || '
cut = None #';'
rand_indices = random.sample(range(len(data)), num_sample)
data1 = [data[i] for i in rand_indices]
# dataset = Dataset_Rhs2Lhs(data1, index=None, te_ratio=0.1, separator=separator, cut=cut).dataset 
# run_name ='ceq_rl_mgpt_v1.2'
dataset = Dataset_Ceq2Ope_simple(data1, index=None, te_ratio=0.1, separator=separator, cut=cut).dataset 
run_name ='ope_simple_dgpt_v1.2'
# hf_model = "gpt2" #"EleutherAI/gpt-neo-1.3B"   #"EleutherAI/gpt-j-6B"  #"distilgpt2"     #"distilgpt2" #'pranav-s/MaterialsBERT'   #'Dagobert42/gpt2-finetuned-material-synthesis'   #'m3rg-iitd/matscibert'   #'HongyangLi/Matbert-finetuned-squad'
model_name = join(hf_usn, run_name)    # '/ope_mgpt_v1.1' #'/tgt_mgpt_v1.4'
tk_model = model_name # set tokenizer model loaded from HF (usually same as hf_model)
load_pretrained=False   # If True, load the model from 'model_name'. Else, load the pre-trained model from hf_model. 
pad_tokenizer=True
save_indices = True

#%%
# load tokenizer
tokenizer = AutoTokenizer.from_pretrained(tk_model) 
if pad_tokenizer:
    tokenizer.pad_token = tokenizer.eos_token   #!
    # tokenizer.add_special_tokens({'pad_token': '[PAD]'})  # checkk if we need this line. 

def tokenize_function(examples):
    return tokenizer(examples["text"], padding=True, truncation=True, return_tensors="pt")  # padding="max_length"

# tokenized dataset
tokenized_datasets = dataset.map(tokenize_function, batched=True, remove_columns=dataset["train"].column_names,)
small_train_dataset = tokenized_datasets["train"].shuffle(seed=seedn)
small_eval_dataset = tokenized_datasets["test"].shuffle(seed=seedn)

#%%
# load model
model = AutoModelForCausalLM.from_pretrained(model_name).to(device)

#%%
# Inference using trained model 
idx = 50
data_source = 'test'  
out_type='add'  # {'type': 'add', 'value': 50}, {'type': 'mul', 'value': 1.2}
out_size = 80 # 120, 2.5
remove_header=False
post_cut = ';'
print(idx)
print('<<our prediction>>')
output=show_one_test(model, dataset, idx, tokenizer, set_length={'type': out_type, 'value': out_size}, 
                     separator=separator, remove_header=remove_header, cut=post_cut, source=data_source, device=device)
print('gtruth: ', output['text']) 
print('answer: ', output['answer'])

label = output['label']
len_label = len(label)
eq_pred = output['answer'][len_label:]
eq_gt = output['text'][len_label:]
similarity_reactants, similarity_products, overall_similarity = equation_similarity(eq_gt, eq_pred, whole_equation=False, split='==')
print(f"(average) Reactants Similarity: {similarity_reactants:.2f}, Products Similarity: {similarity_products:.2f}, Overall Similarity: {overall_similarity:.2f}")

#%%
num_sample = len(dataset[data_source])
sim_reacs, sim_prods, sim_all = [], [], []
chem_dict = {el:[] for el in chemical_symbols}

for idx in tqdm(range(num_sample), desc="Processing"):
    output=show_one_test(model, dataset, idx, tokenizer, set_length={'type': out_type, 'value': out_size}, 
                     separator=separator, remove_header=remove_header, cut=post_cut, source=data_source, device=device)
    label = output['label']
    len_label = len(label)
    eq_pred = output['answer'][len_label:]
    eq_gt = output['text'][len_label:]
    similarity_reactants, similarity_products, overall_similarity = equation_similarity(eq_gt, eq_pred, whole_equation=True, split='==')
    sim_reacs.append(similarity_reactants)
    sim_prods.append(similarity_products)
    sim_all.append(overall_similarity)
    label_elements = find_atomic_species(label)
    for el in label_elements:
        chem_dict[el].append(overall_similarity)

print(model_name)
print(f"(average) Reactants Similarity: {np.mean(sim_reacs):.2f}, Products Similarity: {np.mean(sim_prods):.2f}, Overall Similarity: {np.mean(sim_all):.2f}")
chem_mean_dict = {key: float(np.mean(value)) for key, value in chem_dict.items() if value}
header = run_name + '_' + data_source #'r2l_mean'
filename = f'./save/{header}_{num_sample}.csv'
save_dict_as_csv(chem_mean_dict, filename)
print(f"Dictionary saved as {filename}")

from utils.periodic_trends import plotter
p = plotter(filename, output_filename=f'./save/{header}_{num_sample}.html')


# %%
# model view
from transformers import utils as t_utils
from bertviz import model_view, head_view
t_utils.logging.set_verbosity_error()  # Suppress standard warnings

input_text = output['answer']
model1 = AutoModelForCausalLM.from_pretrained(model_name, output_attentions=True).to(device)
inputs = tokenizer.encode(input_text, return_tensors='pt').to(device)  # Tokenize input text
outputs = model1(inputs)  # Run model
attention = outputs[-1]  # Retrieve attention from model outputs
tokens = tokenizer.convert_ids_to_tokens(inputs[0])  # Convert input ids to token strings

model_view(attention, tokens)  # Display model view
#%%
# head view
head_view(attention, tokens)
#%%
