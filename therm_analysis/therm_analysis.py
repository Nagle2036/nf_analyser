#%%

# Could the participants move the thermometer? Count successful movement as above 5 for more than half the time??
# How did this differ between guilt and indignation tasks?
# How did this differ between the two intervention groups?
# Did it vary based on any demographic or clinical factors?
# Did their actual success correlate with perceived success?
# Does thermometer movement success change between run 2 and run 3? i.e. Do participants reach somewhat of a breakthrough moment?
# Try different metrics for thermometer movement success (e.g. mean level, median level, level stability, level stability + mean / median level). Can also include a threshold for successful movement which is based on the movement of the thermometer if left to chance(?). Maybe favour mean over median because it is not possible to have major outliers in the data (the thermometer level can only be between 0 and 10).
# Can also try: number of volumes where thermometer level was above 5. Or plot histogram of the frequency of different thermometer levels. Can include levels that are also outside of the thermometer range, and have these values in a slightly more faded colour.
# Find amount of time that participant spent above or below thermometer range to test whether thermometer range was suitable.
# Does thermometer movement success vary in accordance with memory intensity?
# Test if MeanSignal stabilises each time during rest blocks.
# Clearly define MeanSignal, Baseline, Value, Thermometer Level etc from tbv_script text file.
# Calculate the average number of blocks that the thermometer goes up or down each volume, in order to ascertain how erratically or stably the thermometer is moving. 
# Could create a heatmap overlayed onto the thermometer in order to provide a visual demonstration of the thermometer levels that were most frequently occupied.
# How well does thermometer success correlate with the different techniques used. Can try to classify the qualitative reports into several categories of techniques.
# Does perceived success correlate with any demographic or clinical factors?
# Does actual or perceived success correlate with improvements in self-esteem / depression ratings?
# If you have high success with guilt thermometer, does that predict low success with indignation thermometer, and vice versa. I.e. is it difficult to be good at moving thermometer under both conditions, or is one condition always favoured.

#%% Step 1: Extract data and execute statistical tests for main experimental variables (i.e. guilt/indignation task, intervention group, run start/end)

import pandas as pd
from plotnine import *
from scipy import stats
import matplotlib.pyplot as plt
import numpy as np
import math
from pingouin import mixed_anova
from statsmodels.stats import multitest


#%%

ecrf_path = r'C:\Users\alexn\OneDrive\Documents\1. Work\5. (2021-) Sussex PhD\Work\Neurofeedback\Participant Data\mri_processor\therm_analysis\ecrf_data.xlsx'
therm_path = r'C:\Users\alexn\OneDrive\Documents\1. Work\5. (2021-) Sussex PhD\Work\Neurofeedback\Participant Data\mri_processor\therm_analysis\therm_data.xlsx'
ecrf_data = pd.read_excel(ecrf_path, index_col='Unnamed: 0')
therm_data = pd.read_excel(therm_path, index_col='Unnamed: 0')
row_to_copy = ecrf_data.loc['intervention', :]
therm_data.loc['intervention', :] = row_to_copy
participants = ['P004', 'P006', 'P020', 'P030', 'P059', 'P078', 'P093', 'P094', 'P100', 'P107', 'P122', 'P125', 'P127', 'P128', 'P136', 'P145', 'P155', 'P199', 'P215']

guilt_lvl_mean_list = []
indig_lvl_mean_list = []
guilt_val_mean_list = []
indig_val_mean_list = []
a_guilt_lvl_mean_list = []
b_guilt_lvl_mean_list = []
a_indig_lvl_mean_list = []
b_indig_lvl_mean_list = []
a_guilt_indig_lvl_mean_list = []
b_guilt_indig_lvl_mean_list = []
runstart_lvl_mean_list = []
runend_lvl_mean_list = []
r2_runstart_lvl_mean_list = []
r2_runend_lvl_mean_list = []
r3_runstart_lvl_mean_list = []
r3_runend_lvl_mean_list = []
r2_runstart_val_mean_list = []
r2_runend_val_mean_list = []
r3_runstart_val_mean_list = []
r3_runend_val_mean_list = []
condition_p_values = []
run_p_values = []

for participant in participants:
    if participant in therm_data.columns:
        current_column = therm_data[participant]
        
        guilt_lvl_rows = therm_data.index.astype(str).str.contains('guilt.*lvl', case=False, regex=True)
        indig_lvl_rows = therm_data.index.astype(str).str.contains('indig.*lvl', case=False, regex=True)
        guilt_indig_lvl_rows = therm_data.index.astype(str).str.contains('guilt.*lvl|indig.*lvl', case=False, regex=True)
        guilt_val_rows = therm_data.index.astype(str).str.contains('guilt.*val', case=False, regex=True)
        indig_val_rows = therm_data.index.astype(str).str.contains('indig.*val', case=False, regex=True)
        guilt_indig_val_rows = therm_data.index.astype(str).str.contains('guilt.*val|indig.*val', case=False, regex=True)
        a_rows = therm_data.loc['intervention', participant] == 'a'   
        b_rows = therm_data.loc['intervention', participant] == 'b'
        r2_runstart_lvl_rows = therm_data.index.astype(str).str.contains('r2.*first.*lvl', case=False, regex=True)
        r2_runend_lvl_rows = therm_data.index.astype(str).str.contains('r2.*second.*lvl', case=False, regex=True)
        r3_runstart_lvl_rows = therm_data.index.astype(str).str.contains('r3.*first.*lvl', case=False, regex=True)
        r3_runend_lvl_rows = therm_data.index.astype(str).str.contains('r3.*second.*lvl', case=False, regex=True)
        runstart_lvl_rows = therm_data.index.astype(str).str.contains('first.*lvl', case=False, regex=True)
        runend_lvl_rows = therm_data.index.astype(str).str.contains('second.*lvl', case=False, regex=True)
        r2_runstart_val_rows = therm_data.index.astype(str).str.contains('r2.*first.*val', case=False, regex=True)
        r2_runend_val_rows = therm_data.index.astype(str).str.contains('r2.*second.*val', case=False, regex=True)
        r3_runstart_val_rows = therm_data.index.astype(str).str.contains('r3.*first.*val', case=False, regex=True)
        r3_runend_val_rows = therm_data.index.astype(str).str.contains('r3.*second.*val', case=False, regex=True)
        runstart_val_rows = therm_data.index.astype(str).str.contains('first.*val', case=False, regex=True)
        runend_val_rows = therm_data.index.astype(str).str.contains('second.*val', case=False, regex=True)
        
        guilt_lvl_data = therm_data.loc[guilt_lvl_rows, [participant]]
        indig_lvl_data = therm_data.loc[indig_lvl_rows, [participant]]
        guilt_indig_lvl_data = therm_data.loc[guilt_indig_lvl_rows, [participant]]
        guilt_val_data = therm_data.loc[guilt_val_rows, [participant]]
        indig_val_data = therm_data.loc[indig_val_rows, [participant]]
        guilt_indig_val_data = therm_data.loc[guilt_indig_val_rows, [participant]]
        a_guilt_lvl_data = current_column[guilt_lvl_rows & a_rows]
        a_indig_lvl_data = current_column[indig_lvl_rows & a_rows]
        a_guilt_indig_lvl_data = pd.concat([a_guilt_lvl_data, a_indig_lvl_data])
        b_guilt_lvl_data = current_column[guilt_lvl_rows & b_rows]
        b_indig_lvl_data = current_column[indig_lvl_rows & b_rows]
        b_guilt_indig_lvl_data = pd.concat([b_guilt_lvl_data, b_indig_lvl_data])
        a_guilt_val_data = current_column[guilt_val_rows & a_rows]
        a_indig_val_data = current_column[indig_val_rows & a_rows]
        a_guilt_indig_val_data = pd.concat([a_guilt_val_data, a_indig_val_data])
        b_guilt_val_data = current_column[guilt_val_rows & b_rows]
        b_indig_val_data = current_column[indig_val_rows & b_rows]
        b_guilt_indig_val_data = pd.concat([b_guilt_val_data, b_indig_val_data])
        r2_runstart_lvl_data = therm_data.loc[r2_runstart_lvl_rows, [participant]]
        r2_runend_lvl_data = therm_data.loc[r2_runend_lvl_rows, [participant]]
        r3_runstart_lvl_data = therm_data.loc[r3_runstart_lvl_rows, [participant]]
        r3_runend_lvl_data = therm_data.loc[r3_runend_lvl_rows, [participant]]
        runstart_lvl_data = therm_data.loc[runstart_lvl_rows, [participant]]
        runend_lvl_data = therm_data.loc[runend_lvl_rows, [participant]]
        r2_runstart_val_data = therm_data.loc[r2_runstart_val_rows, [participant]]
        r2_runend_val_data = therm_data.loc[r2_runend_val_rows, [participant]]
        r3_runstart_val_data = therm_data.loc[r3_runstart_val_rows, [participant]]
        r3_runend_val_data = therm_data.loc[r3_runend_val_rows, [participant]]
        runstart_val_data = therm_data.loc[runstart_val_rows, [participant]]
        runend_val_data = therm_data.loc[runend_val_rows, [participant]]
        
        guilt_lvl_mean = guilt_lvl_data.mean(axis=0)
        indig_lvl_mean = indig_lvl_data.mean(axis=0)
        guilt_indig_lvl_mean = guilt_indig_lvl_data.mean(axis=0)
        guilt_val_mean = guilt_val_data.mean(axis=0)
        indig_val_mean = guilt_val_data.mean(axis=0)
        guilt_indig_val_mean = guilt_indig_val_data.mean(axis=0)
        a_guilt_lvl_mean = a_guilt_lvl_data.mean(axis=0)
        a_indig_lvl_mean = a_indig_lvl_data.mean(axis=0)
        a_guilt_indig_lvl_mean = a_guilt_indig_lvl_data.mean(axis=0)
        b_guilt_lvl_mean = b_guilt_lvl_data.mean(axis=0)
        b_indig_lvl_mean = b_indig_lvl_data.mean(axis=0)
        b_guilt_indig_lvl_mean = b_guilt_indig_lvl_data.mean(axis=0)
        a_guilt_val_mean = a_guilt_val_data.mean(axis=0)
        a_indig_val_mean = a_indig_val_data.mean(axis=0)
        a_guilt_indig_val_mean = a_guilt_indig_val_data.mean(axis=0)
        b_guilt_val_mean = b_guilt_val_data.mean(axis=0)
        b_indig_val_mean = b_indig_val_data.mean(axis=0)
        b_guilt_indig_val_mean = b_guilt_indig_val_data.mean(axis=0)
        r2_runstart_lvl_mean = r2_runstart_lvl_data.mean(axis=0)
        r2_runend_lvl_mean = r2_runend_lvl_data.mean(axis=0)
        r3_runstart_lvl_mean = r3_runstart_lvl_data.mean(axis=0)
        r3_runend_lvl_mean = r3_runend_lvl_data.mean(axis=0)
        runstart_lvl_mean = runstart_lvl_data.mean(axis=0)
        runend_lvl_mean = runend_lvl_data.mean(axis=0)
        r2_runstart_val_mean = r2_runstart_val_data.mean(axis=0)
        r2_runend_val_mean = r2_runend_val_data.mean(axis=0)
        r3_runstart_val_mean = r3_runstart_val_data.mean(axis=0)
        r3_runend_val_mean = r3_runend_val_data.mean(axis=0)
        runstart_val_mean = runstart_val_data.mean(axis=0)
        runend_val_mean = runend_val_data.mean(axis=0)
        
        guilt_lvl_mean_list.append(guilt_lvl_mean.values[0])
        indig_lvl_mean_list.append(indig_lvl_mean.values[0])
        a_guilt_lvl_mean_list.append(a_guilt_lvl_mean)
        b_guilt_lvl_mean_list.append(b_guilt_lvl_mean)
        a_indig_lvl_mean_list.append(a_indig_lvl_mean)
        b_indig_lvl_mean_list.append(b_indig_lvl_mean)
        a_guilt_indig_lvl_mean_list.append(a_guilt_indig_lvl_mean)
        b_guilt_indig_lvl_mean_list.append(b_guilt_indig_lvl_mean)
        runstart_lvl_mean_list.append(runstart_lvl_mean.values[0])
        runend_lvl_mean_list.append(runend_lvl_mean.values[0])
    
        _, guilt_lvl_shap_p = stats.shapiro(guilt_lvl_data.values.flatten())
        _, indig_lvl_shap_p = stats.shapiro(indig_lvl_data.values.flatten())
        
        if guilt_lvl_shap_p > 0.05 and indig_lvl_shap_p > 0.05:
            _, condition_p_value = stats.ttest_rel(guilt_lvl_data.values.flatten(), indig_lvl_data.values.flatten())
            condition_p_values.append(condition_p_value)
        else:
            _, condition_p_value = stats.wilcoxon(guilt_lvl_data.values.flatten(), indig_lvl_data.values.flatten())
            condition_p_values.append(condition_p_value)
    else:
        print(f"Participant {participant} not found in the DataFrame.")

#%% Step 2: Plot the overall mean thermometer levels for guilt and indignation conditions.

guilt_lvl_mean_overall = np.mean(guilt_lvl_mean_list)
indig_lvl_mean_overall = np.mean(indig_lvl_mean_list)
_, guilt_lvl_mean_shap_p = stats.shapiro(guilt_lvl_mean_list)
_, indig_lvl_mean_shap_p = stats.shapiro(indig_lvl_mean_list)
if guilt_lvl_mean_shap_p and indig_lvl_mean_shap_p > 0.05:
    _, p_value = stats.ttest_rel(guilt_lvl_mean_list, indig_lvl_mean_list)
else:
    _, p_value = stats.wilcoxon(guilt_lvl_mean_list, indig_lvl_mean_list)
plot_data = pd.DataFrame({'Condition': ['Guilt', 'Indignation'], 'Mean': [guilt_lvl_mean_overall, indig_lvl_mean_overall]})
overall_condition_mean_plot = (ggplot(plot_data, aes(x='Condition', y='Mean')) + 
                     geom_bar(stat='identity', position='dodge') + 
                     theme_classic() +
                     labs(title='Mean of Thermometer Levels Across All Participants for Guilt and Indignation Conditions.') +
                     scale_y_continuous(expand=(0, 0), limits=[0,4], breaks=[0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0])
                     )
if p_value < 0.001:
    overall_condition_mean_plot = overall_condition_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="***", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.01:
    overall_condition_mean_plot = overall_condition_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="**", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.05:
    overall_condition_mean_plot = overall_condition_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="*", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")    
print(overall_condition_mean_plot)
overall_condition_mean_plot.save('overall_condition_mean_plot.png')
overall_condition_mean_plot.draw()

#%% Step 3: Plot the overall mean thermometer levels for a and b interventions.

a_guilt_indig_lvl_mean_list = [value for value in a_guilt_indig_lvl_mean_list if not math.isnan(value)]
b_guilt_indig_lvl_mean_list = [value for value in b_guilt_indig_lvl_mean_list if not math.isnan(value)]
a_guilt_indig_lvl_mean_overall = np.mean(a_guilt_indig_lvl_mean_list)
b_guilt_indig_lvl_mean_overall = np.mean(b_guilt_indig_lvl_mean_list)
_, a_guilt_indig_lvl_mean_shap_p = stats.shapiro(a_guilt_indig_lvl_mean_list)
_, b_guilt_indig_lvl_mean_shap_p = stats.shapiro(b_guilt_indig_lvl_mean_list)
if a_guilt_indig_lvl_mean_shap_p and b_guilt_indig_lvl_mean_shap_p > 0.05:
    _, p_value = stats.ttest_ind(a_guilt_indig_lvl_mean_list, b_guilt_indig_lvl_mean_list)
else:
    _, p_value = stats.wilcoxon(a_guilt_indig_lvl_mean_list, b_guilt_indig_lvl_mean_list)
plot_data = pd.DataFrame({'Intervention': ['A', 'B'], 'Mean': [a_guilt_indig_lvl_mean_overall, b_guilt_indig_lvl_mean_overall]})
overall_intervention_mean_plot = (ggplot(plot_data, aes(x='Intervention', y='Mean')) + 
                     geom_bar(stat='identity', position='dodge') + 
                     theme_classic() +
                     labs(title='Mean of Thermometer Levels Across All Participants for Interventions A and B.') +
                     scale_y_continuous(expand=(0, 0), limits=[0,4], breaks=[0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0])
                     )
if p_value < 0.001:
    overall_intervention_mean_plot = overall_intervention_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="***", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.01:
    overall_intervention_mean_plot = overall_intervention_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="**", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.05:
    overall_intervention_mean_plot = overall_intervention_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="*", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")    
print(overall_intervention_mean_plot)
overall_intervention_mean_plot.save('overall_intervention_mean_plot.png')
overall_intervention_mean_plot.draw()

#%% Step 4: Plot the mean thermometer levels for a and b intervention groups for each task condition.

a_guilt_lvl_mean_list = [value for value in a_guilt_lvl_mean_list if not math.isnan(value)]
b_guilt_lvl_mean_list = [value for value in b_guilt_lvl_mean_list if not math.isnan(value)]
a_indig_lvl_mean_list = [value for value in a_indig_lvl_mean_list if not math.isnan(value)]
b_indig_lvl_mean_list = [value for value in b_indig_lvl_mean_list if not math.isnan(value)]
a_guilt_lvl_mean_overall = np.mean(a_guilt_lvl_mean_list)
b_guilt_lvl_mean_overall = np.mean(b_guilt_lvl_mean_list)
a_indig_lvl_mean_overall = np.mean(a_indig_lvl_mean_list)
b_indig_lvl_mean_overall = np.mean(b_indig_lvl_mean_list)

_, a_guilt_lvl_mean_shap_p = stats.shapiro(a_guilt_lvl_mean_list)
_, b_guilt_lvl_mean_shap_p = stats.shapiro(b_guilt_lvl_mean_list)
_, a_indig_lvl_mean_shap_p = stats.shapiro(a_indig_lvl_mean_list)
_, b_indig_lvl_mean_shap_p = stats.shapiro(b_indig_lvl_mean_list)

if a_guilt_lvl_mean_shap_p and b_guilt_lvl_mean_shap_p > 0.05:
    _, ab_guilt_p_value = stats.ttest_ind(a_guilt_lvl_mean_list, b_guilt_lvl_mean_list)
else:
    _, ab_guilt_p_value = stats.mannwhitneyu(a_guilt_lvl_mean_list, b_guilt_lvl_mean_list)
if a_indig_lvl_mean_shap_p and b_indig_lvl_mean_shap_p > 0.05:
    _, ab_indig_p_value = stats.ttest_ind(a_indig_lvl_mean_list, b_indig_lvl_mean_list)
else:
    _, ab_indig_p_value = stats.mannwhitneyu(a_indig_lvl_mean_list, b_indig_lvl_mean_list)
if a_guilt_lvl_mean_shap_p and a_indig_lvl_mean_shap_p > 0.05:
    _, a_guiltindig_p_value = stats.ttest_ind(a_guilt_lvl_mean_list, a_indig_lvl_mean_list)
else:
    _, a_guiltindig_p_value = stats.mannwhitneyu(a_guilt_lvl_mean_list, a_indig_lvl_mean_list)
if b_guilt_lvl_mean_shap_p and b_indig_lvl_mean_shap_p > 0.05:
    _, b_guiltindig_p_value = stats.ttest_ind(b_guilt_lvl_mean_list, b_indig_lvl_mean_list)
else:
    _, b_guiltindig_p_value = stats.mannwhitneyu(b_guilt_lvl_mean_list, b_indig_lvl_mean_list)

p_values = [ab_guilt_p_value, ab_indig_p_value, a_guiltindig_p_value, b_guiltindig_p_value]
reject, adjusted_p_values, _, _ = multitest.multipletests(p_values, alpha=0.05, method='fdr_bh')
for i, (p_value, adj_p_value, rej) in enumerate(zip(p_values, adjusted_p_values, reject)):
    print(f"Comparison {i + 1}: p-value = {p_value:.4f}, Adjusted p-value = {adj_p_value:.4f}, Reject H0 = {rej}")

plot_data = pd.DataFrame({'Condition': ['Guilt', 'Guilt', 'Indignation', 'Indignation'], 'Group': ['a', 'b', 'a', 'b'], 'Mean': [a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall, a_indig_lvl_mean_overall, b_indig_lvl_mean_overall]})
condition_intervention_mean_plot = (ggplot(plot_data, aes(x='Condition', y='Mean', fill='Group')) +
    geom_bar(stat='identity', position='dodge') + 
    theme_classic() +
    labs(title='Mean of Thermometer Levels Across All Participants for Guilt and Indignation in Interventions A and B.') +
    scale_y_continuous(expand=(0, 0), limits=[0,4], breaks=[0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0])
    )

if ab_guilt_p_value < 0.001:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.0, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.3, label="***", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.25, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.25, color="black")
elif ab_guilt_p_value < 0.01:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.0, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.3, label="**", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.25, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.25, color="black")
elif ab_guilt_p_value < 0.0125:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.0, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.3, label="*", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.25, y=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, b_guilt_lvl_mean_overall) + 0.25, color="black")    

if ab_indig_p_value < 0.001:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=2.0, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.3, label="***", size=16, color="black") + \
        annotate("segment", x=1.75, xend=2.25, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) +0.25, yend=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.25, color="black")
elif ab_indig_p_value < 0.01:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=2.0, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.3, label="**", size=16, color="black") + \
        annotate("segment", x=1.75, xend=2.25, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) +0.25, yend=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.25, color="black")
elif ab_indig_p_value < 0.0125:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=2.0, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.3, label="*", size=16, color="black") + \
        annotate("segment", x=1.75, xend=2.25, y=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) +0.25, yend=max(a_indig_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.25, color="black")    

if a_guiltindig_p_value < 0.001:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.25, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.3, label="***", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.75, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.25, color="black")
elif a_guiltindig_p_value < 0.01:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.25, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.3, label="**", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.75, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.25, color="black")
elif a_guiltindig_p_value < 0.0125:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.25, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.3, label="*", size=16, color="black") + \
        annotate("segment", x=0.75, xend=1.75, y=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) +0.25, yend=max(a_guilt_lvl_mean_overall, a_indig_lvl_mean_overall) + 0.25, color="black")    

if b_guiltindig_p_value < 0.001:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.7, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.65, label="***", size=16, color="black") + \
        annotate("segment", x=1.2, xend=2.25, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) +0.6, yend=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.6, color="black")
elif b_guiltindig_p_value < 0.01:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.7, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.65, label="**", size=16, color="black") + \
        annotate("segment", x=1.2, xend=2.25, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) +0.6, yend=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.6, color="black")
elif b_guiltindig_p_value < 0.0125:
    condition_intervention_mean_plot = condition_intervention_mean_plot + annotate("text", x=1.7, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.65, label="*", size=16, color="black") + \
        annotate("segment", x=1.2, xend=2.25, y=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) +0.6, yend=max(b_guilt_lvl_mean_overall, b_indig_lvl_mean_overall) + 0.6, color="black")    

print(condition_intervention_mean_plot)
condition_intervention_mean_plot.save('condition_intervention_mean_plot.png')
condition_intervention_mean_plot.draw()


#%% Step 4: Plot the mean thermometer levels for guilt and indignation conditions for each participant.

plot_data = pd.DataFrame({
    'Participant': participants * 2,
    'Mean_Value': guilt_lvl_mean_list + indig_lvl_mean_list,
    'Condition': ['Guilt'] * len(participants) + ['Indignation'] * len(participants),
    'Significance': ['' for _ in range(len(participants) * 2)]
})
for idx, condition_p_value in enumerate(condition_p_values):
    if condition_p_value < 0.001:
        plot_data.at[idx, 'Significance'] = '***'
    elif condition_p_value < 0.01:
        plot_data.at[idx, 'Significance'] = '**'
    elif condition_p_value < 0.05:
        plot_data.at[idx, 'Significance'] = '*'
participant_condition_mean_plot = (
    ggplot(plot_data, aes(x='Participant', y='Mean_Value', fill='Condition')) +
    geom_bar(stat='identity', position='dodge') +
    theme_classic() +
    labs(title='Mean Thermometer Levels for Guilt vs Indignation Conditions', x='Participant', y='Mean Value') +
    theme(axis_text_x=element_text(rotation=45, hjust=1), text=element_text(size=12, color='blue'), axis_title=element_text(size=14, face='bold')) +
    scale_y_continuous(expand=(0, 0), limits=[0,6]) +
    geom_text(
        aes(x='Participant', y='Mean_Value', label='Significance'),
        position=position_dodge(width=0.9),
        color='black',
        size=12,
        ha='center',
        va='bottom',
        show_legend=False) +
    labs(subtitle='Note: move asterisks be over the middle of each pair of bars.'))
print(participant_condition_mean_plot)
participant_condition_mean_plot.save('mean_values_plot_guilt_vs_indig.png')
participant_condition_mean_plot.draw()

#%% Step 5: Plot the overall mean thermometer levels for 1st and 2nd halves of each run.

runstart_lvl_mean_overall = np.mean(runstart_lvl_mean_list)
runend_lvl_mean_overall = np.mean(runend_lvl_mean_list)

_, runstart_lvl_mean_shap_p = stats.shapiro(runstart_lvl_mean_list)
_, runend_lvl_mean_shap_p = stats.shapiro(runend_lvl_mean_list)
if runstart_lvl_mean_shap_p and runend_lvl_mean_shap_p > 0.05:
    _, p_value = stats.ttest_rel(runstart_lvl_mean_list, runend_lvl_mean_list)
else:
    _, p_value = stats.wilcoxon(runstart_lvl_mean_list, runend_lvl_mean_list)
plot_data = pd.DataFrame({'Condition': pd.Categorical(['Run Start', 'Run End'], categories=['Run Start', 'Run End']), 'Mean': [runstart_lvl_mean_overall, runend_lvl_mean_overall]})
run_startend_mean_plot = (ggplot(plot_data, aes(x='Condition', y='Mean')) + 
                     geom_bar(stat='identity', position='dodge') + 
                     theme_classic() +
                     labs(title='Mean of Thermometer Values Across All Participants Comparing Run Start and Run End.') +
                     scale_y_continuous(expand=(0, 0), limits=[0,4], breaks=[0.0,0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0])
                     )
if p_value < 0.001:
    run_startend_mean_plot = run_startend_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="***", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.01:
    run_startend_mean_plot = run_startend_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="**", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")
elif p_value < 0.05:
    run_startend_mean_plot = run_startend_mean_plot + annotate("text", x=1.5, y=max(plot_data['Mean']) + 0.6, label="*", size=16, color="black") + \
        annotate("segment", x=1, xend=2, y=max(plot_data['Mean']) +0.5, yend=max(plot_data['Mean']) + 0.5, color="black")    
print(run_startend_mean_plot)
run_startend_mean_plot.save('run_startend_mean_plot.png')
run_startend_mean_plot.draw()

#%% Step 5: Plot histogram of thermometer level frequencies.

for participant in participants:
    if participant in therm_data.columns:
        current_column = therm_data[participant]
        guilt_val_rows = therm_data.index.astype(str).str.contains('guilt.*val', case=False, regex=True)
        indig_val_rows = therm_data.index.astype(str).str.contains('indig.*val', case=False, regex=True)
        guilt_indig_val_rows = therm_data.index.astype(str).str.contains('guilt.*val|indig.*val', case=False, regex=True)
        a_rows = therm_data.loc['intervention', participant] == 'a'   
        b_rows = therm_data.loc['intervention', participant] == 'b'  
        
        guilt_val_data = therm_data.loc[guilt_lvl_rows, [participant]]
        indig_val_data = therm_data.loc[indig_lvl_rows, [participant]]
        guilt_indig_val_data = therm_data.loc[guilt_indig_val_rows, [participant]]
        a_guilt_val_data = current_column[guilt_val_rows & a_rows]
        a_indig_val_data = current_column[indig_val_rows & a_rows]
        a_guilt_indig_val_data = pd.concat([a_guilt_val_data, a_indig_val_data])
        b_guilt_val_data = current_column[guilt_val_rows & b_rows]
        b_indig_val_data = current_column[indig_val_rows & b_rows]
        b_guilt_indig_val_data = pd.concat([b_guilt_val_data, b_indig_val_data])



histogram_plot = ggplot()
        

np.random.seed(42)  # Setting seed for reproducibility
group1_data = np.random.normal(loc=5, scale=2, size=100)
group2_data = np.random.normal(loc=8, scale=2, size=100)

# Create a DataFrame
df = pd.DataFrame({'Group1': group1_data, 'Group2': group2_data})

# Plotting
p = ggplot(df, aes(x='Group1')) + \
    geom_histogram(binwidth=1, fill='blue', alpha=1) + \
    geom_histogram(aes(x='Group2'), binwidth=1, fill='green', alpha=1) + \
    scale_fill_manual(values=['blue', 'green']) + \
    theme_classic()

# Show the plot
print(p)

#%% Perform ANOVA to investigate effects of condition (guilt / indignation), run progress (start / end) and intervention (a / b) on thermometer level.

column_headers = ['participant', 'condition', 'intervention', 'therm_lvl', 'therm_val']
anova_df = pd.DataFrame(columns=column_headers)
for participant in participants:
    if participant in therm_data.columns:
        guilt_indig_lvl_rows = therm_data.index.astype(str).str.contains('guilt.*lvl|indig.*lvl', case=False, regex=True)
        guilt_indig_lvl_data = therm_data.loc[guilt_indig_lvl_rows, [participant]]
        new_values = guilt_indig_lvl_data[participant]
        
        guilt_indig_val_rows = therm_data.index.astype(str).str.contains('guilt.*val|indig.*val', case=False, regex=True)
        guilt_indig_val_data = therm_data.loc[guilt_indig_val_rows, [participant]]
        val_values = guilt_indig_val_data[participant]
        val_values = list(val_values)
        
        index_list = therm_data.index.tolist()
        guiltindig_list = ['guilt' if 'guilt' in value and 'lvl' in value else 'indig' if 'indig' in value and 'lvl' in value else None for value in index_list]
        guiltindig_list = [value for value in guiltindig_list if value is not None]
        
        if therm_data.loc['intervention', participant] == 'a':
            group = 'a'
        else:
            group = 'b'

        if anova_df.empty:
            anova_df = pd.DataFrame({
                'participant': [participant] * len(new_values),
                'condition': guiltindig_list,
                'intervention': [group] * len(new_values),
                'therm_lvl': new_values,
                'therm_val': val_values
            })
        else:
            anova_df = pd.concat([anova_df, pd.DataFrame({
                'participant': [participant] * len(new_values),
                'condition': guiltindig_list,
                'intervention': [group] * len(new_values),
                'therm_lvl': new_values,
                'therm_val': val_values
            })], ignore_index=True)

anova_df['therm_lvl'] = pd.to_numeric(anova_df['therm_lvl'], errors='coerce')
# Define the repeated measures ANOVA model
anova_model = 'therm_lvl ~ C(condition) * C(intervention) + (C(condition) + C(intervention) | participant)'

# Check for sphericity assumption (using pingouin for repeated measures ANOVA)
sphericity_test = mixed_anova(data=anova_df, dv='therm_lvl', within='condition', subject='participant', between='intervention')
epsilon_value = sphericity_test.loc[sphericity_test['Source'] == 'condition', 'eps'].values[0]

# Check for normality assumption using Shapiro-Wilk test
hist = ggplot(anova_df, aes(x='therm_lvl')) + \
    geom_histogram(binwidth=0.1, fill='#75AADB', color='black', alpha=0.7) + \
    theme_classic() + \
    scale_y_continuous(expand=(0, 0)) + \
    ggtitle('Histogram of Therm Level')
print(hist)
hist.save('hist.png')
hist.draw()

p_values = []
normality_passed = True
for (condition, intervention), group_data in anova_df.groupby(['condition', 'intervention']):
    _, p_value = stats.shapiro(group_data['therm_lvl'])
    p_values.append((condition, intervention, p_value))
    if p_value < 0.05:
        normality_passed = False

# Check for homogeneity of variance assumption using Levene's test
_, p_value_levene = stats.levene(anova_df['therm_lvl'][anova_df['condition'] == 'guilt'],
                           anova_df['therm_lvl'][anova_df['condition'] == 'indig'],
                           anova_df['therm_lvl'][anova_df['intervention'] == 'a'],
                           anova_df['therm_lvl'][anova_df['intervention'] == 'b'])

# Apply repeated measures ANOVA or Friedman test based on assumptions
if normality_passed and p_value_levene > 0.05 and epsilon_value > 0.75:
    # Repeated measures ANOVA
    anova_result = mixed_anova(data=anova_df, dv='therm_lvl', within='condition', subject='participant', between='intervention')
    print(anova_result)
else:
    # Non-parametric alternative (Friedman test)
    friedman_results = []

    # Iterate over each level of 'intervention' and perform a Friedman test
    for group, group_data in anova_df.groupby('intervention'):
        result = stats.friedmanchisquare(*[group_data['therm_lvl'] for _, group_data in group_data.groupby('condition')])
        friedman_results.append(result)
    
    # Print the results for each level of 'intervention'
    for intervention, result in zip(anova_df['intervention'].unique(), friedman_results):
        print(f"Friedman test result for intervention {intervention}: {result}")
        
        
from statsmodels.genmod.families import Poisson
from statsmodels.genmod import GLM

formula = 'therm_lvl ~ C(intervention) * C(condition) + (1 | participant)'
model = GLM.from_formula(formula, family=Poisson(), data=anova_df)
results = model.fit()

print(results.summary())

#%%

import pandas as pd
import statsmodels.api as sm
from plotnine import ggplot, aes, geom_point, geom_smooth, facet_wrap

# Assuming you have a DataFrame named 'anova_df' with the given columns
# 'therm_lvl', 'condition', 'intervention', 'participant', and 'index'

# Convert categorical variables to categorical type
anova_df['condition'] = pd.Categorical(anova_df['condition'])
anova_df['intervention'] = pd.Categorical(anova_df['intervention'])
anova_df['participant'] = pd.Categorical(anova_df['participant'])

# Fit a linear mixed model
formula = 'therm_val ~ condition * intervention'
random_formula = '0 + participant'
lmm = sm.MixedLM.from_formula(formula, anova_df, groups=anova_df['participant'], re_formula=random_formula)
result = lmm.fit()

# Plot residuals
anova_df['residuals'] = result.resid
p = ggplot(anova_df, aes(x='index', y='residuals')) + geom_point() + geom_smooth(method='loess') + facet_wrap('~participant')
print(p)

# Check residuals and choose standard errors accordingly
if check_residuals(anova_df['residuals']):
    # If residuals don't look right, fit with robust standard errors
    result = lmm.fit(cov_type='robust')
else:
    # Otherwise, fit with normal standard errors
    result = lmm.fit()

# Print summary
print(result.summary())

# Visualize results
p = ggplot(anova_df, aes(x='condition', y='therm_val', color='intervention')) + geom_point() + geom_smooth(method='lm', se=False)
print(p)