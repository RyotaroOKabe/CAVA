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
from huggingface_hub import login
import pickle as pkl
import matplotlib.pyplot as plt
import pandas as pd

from env_config import *
from utils.data import *
from utils.metrics import *
from utils.plot_data import *

login(hf_api_key_w, add_to_git_credential=True)

#%%
# [1] Load dataset
random.seed(seedn)
sample_ratio = 1
data = json.load(open(data_path, 'r'))
num_sample = int(len(data)*sample_ratio)
separator='<-'    #!
cut = ';' #!
rand_indices = random.sample(range(len(data)), num_sample)
data1 = [data[i] for i in rand_indices]
dataset = Dataset_Rhs2Lhs(data1, index=None, te_ratio=0.1, separator=separator, cut=cut).dataset    #!
run_name = 'B_dgpt2_v1.1.1'   #!
model_name = join(hf_usn, run_name) 
tk_model = model_name # set tokenizer model loaded from HF (usually same as hf_model)
load_pretrained=False   # If True, load the model from 'model_name'. Else, load the pre-trained model from hf_model. 
pad_tokenizer=True
save_indices = True

#%%
# [2] load tokenizer
tokenizer = AutoTokenizer.from_pretrained(tk_model) 
if pad_tokenizer:
    tokenizer.pad_token = tokenizer.eos_token  
    # tokenizer.add_special_tokens({'pad_token': '[PAD]'})  # checkk if we need this line. 

def tokenize_function(examples):
    return tokenizer(examples["text"], padding=True, truncation=True, return_tensors="pt")  # padding="max_length"

# tokenized dataset
tokenized_datasets = dataset.map(tokenize_function, batched=True, remove_columns=dataset["train"].column_names,)
small_train_dataset = tokenized_datasets["train"].shuffle(seed=seedn)
small_eval_dataset = tokenized_datasets["test"].shuffle(seed=seedn)

#%%
# [3] load model
model = AutoModelForCausalLM.from_pretrained(model_name).to(device)
model0 = AutoModelForCausalLM.from_pretrained("distilbert/distilgpt2").to(device)

#%%
# [4] Inference using trained model 
idx = 40
data_source = 'test'  
out_type='mul'  # {'type': 'add', 'value': 50}, {'type': 'mul', 'value': 1.2}
out_size = 2.1 # 120, 2.5
remove_header=False
post_cut = ';'
print(idx)
print('<<our prediction>>')
output=show_one_test(model, dataset, idx, tokenizer, set_length={'type': out_type, 'value': out_size}, 
                     separator=separator, remove_header=remove_header, cut=post_cut, source=data_source, device=device)

label = output['label']
len_label = len(label)
eq_pred = output['answer']
eq_gt = output['text']
if remove_header:
    # eq_pred = eq_pred[len_label:]
    eq_gt = eq_gt[len_label:]
eq_gt = eq_gt.replace('||', '')
eq_pred = eq_pred.replace('||', '')
print('gtruth: ', eq_gt) 
print('answer: ', eq_pred)
similarity_reactants, similarity_products, overall_similarity = equation_similarity(eq_gt, eq_pred, whole_equation=False, split=separator)#['=='])#, separator, '||', '=='])
print(f"(average) Reactants Similarity: {similarity_reactants:.2f}, Products Similarity: {similarity_products:.2f}, Overall Similarity: {overall_similarity:.2f}")

#%%
# [5] Plot element-wise prediction accuracy.
tag = 'v1.1'
num_sample = len(dataset[data_source])
sim_reacs, sim_prods, sim_all = [], [], []
lens_reacs, lens_prods = [], []
chem_dict = {el:[] for el in chemical_symbols}
df = pd.DataFrame(columns=['idx', 'prompt', 'gt', 'pred', 'similarity'])

for idx in tqdm(range(num_sample), desc="Processing"):
    output=show_one_test(model, dataset, idx, tokenizer, set_length={'type': out_type, 'value': out_size}, 
                     separator=separator, remove_header=remove_header, cut=post_cut, source=data_source, device=device)
    label = output['label']
    len_label = len(label)
    eq_pred = output['answer']
    eq_gt = output['text']
    len_reac, len_product = len(eq_gt.split(separator)[1]), len(eq_gt.split(separator)[0])
    lens_reacs.append(len_reac)
    lens_prods.append(len_product)
    if remove_header:
        # eq_pred = eq_pred[len_label:]
        eq_gt = eq_gt[len_label:]
    similarity_reactants, similarity_products, overall_similarity = equation_similarity(eq_gt, eq_pred, whole_equation=False, split=separator)
    sim_reacs.append(similarity_reactants)
    sim_prods.append(similarity_products)
    sim_all.append(overall_similarity)
    label_elements = find_atomic_species(label)
    df = df._append({'idx': idx, 'prompt': label, 'gt': eq_gt, 'pred': eq_pred, 'similarity': overall_similarity}, ignore_index=True)
    for el in label_elements:
        chem_dict[el].append(overall_similarity)

print(model_name)
print(f"(average) Reactants Similarity: {np.mean(sim_reacs):.2f}, Products Similarity: {np.mean(sim_prods):.2f}, Overall Similarity: {np.mean(sim_all):.2f}")
chem_mean_dict = {key: float(np.mean(value)) for key, value in chem_dict.items() if value}
header = run_name + '_' + data_source #'r2l_mean'
filename = f'./save/{header}_{num_sample}_{tag}.csv'
save_dict_as_csv(chem_mean_dict, filename)
print(f"Dictionary saved as {filename}")
# save chem_dict as pkl
with open(f'./save/{header}_{num_sample}_{tag}.pkl', 'wb') as f:
    pkl.dump(chem_dict, f)

from utils.periodic_trends import plotter
p = plotter(filename, output_filename=f'./save/{header}_{num_sample}_{tag}.html', under_value=0, over_value=1)


fig, axs = plt.subplots(1, 2, figsize=(10, 5))
ax = axs[0]
# ax.scatter(lens_reacs, sim_reacs, s=5, color='blue', label='Reactants')
# ax.scatter(lens_reacs, sim_prods, s=5, color='red', label='Products')
ax.scatter(lens_reacs, sim_all, s=5, color=good_colors['green'], label='Overall')
ax.set_xlabel('Wrt reactant lengths', fontsize=14)
ax.set_ylabel('Accuracy', fontsize=14)
# ax.legend()

ax = axs[1]
# ax.scatter(lens_prods, sim_reacs, s=5, color='blue', label='Reactants')
# ax.scatter(lens_prods, sim_prods, s=5, color='red', label='Products')
ax.scatter(lens_prods, sim_all, s=5, color=good_colors['green'], label='Overall')
ax.set_xlabel('Wrt product lengths', fontsize=14)
ax.set_ylabel('Accuracy', fontsize=14)
# ax.legend()

fig.suptitle(f'{header}_{num_sample}_{tag}', fontsize=16)
fig.savefig(f'./save/{header}_{num_sample}_{tag}_scatter.png')

len_data = np.array([lens_reacs, lens_prods, sim_all]).T
np.save(f'./save/{header}_{num_sample}_{tag}_len_data.npy', len_data)

# save df as csv 
df.to_csv(f'./save/{header}_{num_sample}_{tag}_df.csv')

# %%
# [6] model view (optional)
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
