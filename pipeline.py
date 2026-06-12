import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scipy.stats import pearsonr

# Set plot style
sns.set_theme(style="whitegrid")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']

# Paths
raw_dir = "data/raw"
clean_dir = "data/clean"
plots_dir = "plots"

print("--- PHASE 1: DATA SCRUBBING & INTEGRATION ---")

# 1. Load IPM
print("Scrubbing IPM dataset...")
ipm_file = os.path.join(raw_dir, "Indeks Pembangunan Manusia Provinsi Jawa Barat 2024.xlsx")
df_ipm_raw = pd.read_excel(ipm_file)
# Slice rows 48 to 74 (0-indexed 48 to 74 is the 27 Kab/Kota)
df_ipm = df_ipm_raw.iloc[48:75, [1, 2, 3]].copy()
df_ipm.columns = ['Kab_Kota_Raw', 'IPM_2024', 'Laju_IPM']
df_ipm['Kab_Kota_Raw'] = df_ipm['Kab_Kota_Raw'].str.strip()
df_ipm['IPM_2024'] = pd.to_numeric(df_ipm['IPM_2024'], errors='coerce')
df_ipm['Laju_IPM'] = pd.to_numeric(df_ipm['Laju_IPM'], errors='coerce')

# Map to standard names
def standardize_ipm(name):
    if name.startswith("Kabupaten "):
        return name.replace("Kabupaten ", "Kab. ")
    return name
df_ipm['Kab_Kota'] = df_ipm['Kab_Kota_Raw'].apply(standardize_ipm)
df_ipm_final = df_ipm[['Kab_Kota', 'IPM_2024', 'Laju_IPM']].copy()

# 2. Load Poverty
print("Scrubbing Poverty dataset...")
poverty_file = os.path.join(raw_dir, "Jumlah dan Persentase Penduduk Miskin Menurut Kabupaten_Kota di Provinsi Jawa Barat, 2024.xlsx")
df_poverty_raw = pd.read_excel(poverty_file)
df_poverty = df_poverty_raw.iloc[:27, [0, 1, 3, 5]].copy()
df_poverty.columns = ['Kab_Kota_Raw', 'Garis_Kemiskinan_Maret', 'Jumlah_Miskin_Maret_Ribu', 'Persentase_Miskin_Maret']
df_poverty['Kab_Kota_Raw'] = df_poverty['Kab_Kota_Raw'].str.strip()

def standardize_poverty(name):
    if name.startswith("Kota "):
        return name
    return "Kab. " + name
df_poverty['Kab_Kota'] = df_poverty['Kab_Kota_Raw'].apply(standardize_poverty)
df_poverty_final = df_poverty[['Kab_Kota', 'Garis_Kemiskinan_Maret', 'Jumlah_Miskin_Maret_Ribu', 'Persentase_Miskin_Maret']].copy()

# 3. Load Putus Sekolah
print("Scrubbing Putus Sekolah dataset...")
ps_file = os.path.join(raw_dir, "Tab-Putus-Sekolah.xlsx")
df_ps_raw = pd.read_excel(ps_file, sheet_name='Tab-Putus-Sekolah')
# Slices rows 5 to 31 (27 rows)
df_ps = df_ps_raw.iloc[5:32, [2, 9, 15, 22, 29, 36]].copy()
df_ps.columns = ['Kab_Kota_Raw', 'Putus_SD', 'Putus_SMP', 'Putus_SMA', 'Putus_SMK', 'Putus_SLB']
df_ps['Kab_Kota_Raw'] = df_ps['Kab_Kota_Raw'].str.strip()
df_ps['Kab_Kota'] = df_ps['Kab_Kota_Raw'] # Already in standard format

for col in ['Putus_SD', 'Putus_SMP', 'Putus_SMA', 'Putus_SMK', 'Putus_SLB']:
    df_ps[col] = pd.to_numeric(df_ps[col], errors='coerce').fillna(0).astype(int)
df_ps_final = df_ps[['Kab_Kota', 'Putus_SD', 'Putus_SMP', 'Putus_SMA', 'Putus_SMK', 'Putus_SLB']].copy()

# 4. Integrate
print("Merging datasets...")
df_merged = df_ps_final.merge(df_ipm_final, on='Kab_Kota', how='inner')
df_merged = df_merged.merge(df_poverty_final, on='Kab_Kota', how='inner')

print(f"Data integrated successfully. Shape: {df_merged.shape}")
assert df_merged.shape[0] == 27, f"Error: Row count is {df_merged.shape[0]}, expected 27!"
print("Null values after merge:")
print(df_merged.isnull().sum())

print("\n--- PHASE 2: FEATURE ENGINEERING ---")
# 1. Total Putus Sekolah
df_merged['Total_Putus_Sekolah'] = (
    df_merged['Putus_SD'] + 
    df_merged['Putus_SMP'] + 
    df_merged['Putus_SMA'] + 
    df_merged['Putus_SMK'] + 
    df_merged['Putus_SLB']
)

# 2. Penduduk Miskin (Jiwa)
df_merged['Jumlah_Miskin_Jiwa'] = (df_merged['Jumlah_Miskin_Maret_Ribu'] * 1000).astype(int)

# 3. Estimasi Total Penduduk (Jiwa)
df_merged['Estimasi_Total_Penduduk'] = ((df_merged['Jumlah_Miskin_Jiwa'] * 100) / df_merged['Persentase_Miskin_Maret']).astype(int)

# 4. Rasio Putus Sekolah per Jumlah Penduduk Miskin
df_merged['Rasio_Putus_Sekolah_per_Miskin'] = df_merged['Total_Putus_Sekolah'] / df_merged['Jumlah_Miskin_Jiwa']

# 5. Angka Putus Sekolah per 10.000 Penduduk (Dropout Rate)
df_merged['Putus_Sekolah_per_10k_Penduduk'] = (df_merged['Total_Putus_Sekolah'] / df_merged['Estimasi_Total_Penduduk']) * 10000

# Export master table
clean_csv_path = os.path.join(clean_dir, "dataset_bersih.csv")
df_merged.to_csv(clean_csv_path, index=False)
print(f"Clean Master Table saved to: {clean_csv_path}")

print("\n--- PHASE 3: EXPLORATORY DATA ANALYSIS (EDA) ---")
# Correlation analysis
poverty_rate = df_merged['Persentase_Miskin_Maret']
dropout_rate = df_merged['Putus_Sekolah_per_10k_Penduduk']
corr_coeff, p_value = pearsonr(poverty_rate, dropout_rate)
print(f"Pearson Correlation between Poverty Rate and School Dropout Rate (per 10k):")
print(f"  Coefficient: {corr_coeff:.4f}")
print(f"  P-value: {p_value:.4f}")

# Save correlation scatter plot
plt.figure(figsize=(8, 6))
sns.regplot(x=poverty_rate, y=dropout_rate, scatter_kws={'s': 50, 'alpha': 0.8}, line_kws={'color': '#d9534f', 'lw': 2})
plt.title("Correlation between Poverty Rate and School Dropout Rate (per 10k)", fontsize=13, fontweight='bold', pad=15)
plt.xlabel("Persentase Penduduk Miskin (%)", fontsize=11, labelpad=10)
plt.ylabel("Angka Putus Sekolah per 10.000 Penduduk", fontsize=11, labelpad=10)

# Annotate correlation coefficient on plot
plt.text(0.05, 0.95, f"Pearson r = {corr_coeff:.3f}\np-value = {p_value:.4f}", 
         transform=plt.gca().transAxes, fontsize=11, verticalalignment='top',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.8, edgecolor='gray'))

# Add Kabupaten labels to dots (for a few points, or all since it's just 27)
for i, txt in enumerate(df_merged['Kab_Kota']):
    # Selectively label to avoid overcrowding
    if df_merged.loc[i, 'Persentase_Miskin_Maret'] > 9.5 or df_merged.loc[i, 'Putus_Sekolah_per_10k_Penduduk'] > 1.3 or txt in ['Kota Bandung', 'Kota Bekasi', 'Kab. Cianjur', 'Kab. Bogor']:
        plt.annotate(txt.replace("Kab. ", "").replace("Kota ", ""), 
                     (df_merged.loc[i, 'Persentase_Miskin_Maret'], df_merged.loc[i, 'Putus_Sekolah_per_10k_Penduduk']),
                     textcoords="offset points", xytext=(0,5), ha='center', fontsize=8, fontweight='semibold')

plt.tight_layout()
corr_plot_path = os.path.join(plots_dir, "poverty_dropout_correlation.png")
plt.savefig(corr_plot_path, dpi=300)
plt.close()
print(f"Correlation plot saved to: {corr_plot_path}")

print("\n--- PHASE 4: CLUSTERING & EVALUATION ---")
# 1. Select features for clustering
cluster_features = ['Putus_Sekolah_per_10k_Penduduk', 'Persentase_Miskin_Maret', 'IPM_2024']
X = df_merged[cluster_features].copy()

# 2. Standardize features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 3. Determine number of clusters (Elbow & Silhouette)
inertia = []
k_range = range(1, 11)
for k in k_range:
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X_scaled)
    inertia.append(kmeans.inertia_)

# Save Elbow Plot
plt.figure(figsize=(7, 4.5))
plt.plot(k_range, inertia, 'o-', color='#337ab7', lw=2)
plt.title("Elbow Method for Optimal k", fontsize=12, fontweight='bold', pad=12)
plt.xlabel("Number of Clusters (k)", fontsize=10)
plt.ylabel("Inertia (Within-Cluster Sum of Squares)", fontsize=10)
plt.xticks(k_range)
plt.tight_layout()
elbow_plot_path = os.path.join(plots_dir, "elbow_plot.png")
plt.savefig(elbow_plot_path, dpi=300)
plt.close()
print(f"Elbow plot saved to: {elbow_plot_path}")

# Run K-Means with k=3
kmeans_3 = KMeans(n_clusters=3, random_state=42, n_init=10)
df_merged['Cluster'] = kmeans_3.fit_predict(X_scaled)
silhouette_avg = silhouette_score(X_scaled, df_merged['Cluster'])
print(f"K-Means Clustering with k=3:")
print(f"  Silhouette Score: {silhouette_avg:.4f}")

# Profile the clusters to map labels: High, Medium, Low Risk
cluster_centers = df_merged.groupby('Cluster')[cluster_features].mean()
print("\nCluster Means:")
print(cluster_centers)

# Assign risk labels based on average values
# High Risk: High poverty, High dropout rate, Low IPM
# Low Risk: Low poverty, Low dropout rate, High IPM
# We sort clusters by (Persentase_Miskin_Maret + Putus_Sekolah_per_10k_Penduduk * constant - IPM_2024)
# Better yet, let's look at the ranks of center values
centers_df = cluster_centers.copy()
# Normalize centers for a quick ranking index: higher means higher risk
centers_norm = (centers_df - centers_df.min()) / (centers_df.max() - centers_df.min() + 1e-9)
centers_norm['IPM_2024'] = 1.0 - centers_norm['IPM_2024'] # Higher IPM = Lower Risk
risk_index = centers_norm['Persentase_Miskin_Maret'] + centers_norm['Putus_Sekolah_per_10k_Penduduk'] + centers_norm['IPM_2024']
sorted_clusters = risk_index.sort_values().index.tolist()

risk_mapping = {
    sorted_clusters[0]: 'Risiko Rendah',
    sorted_clusters[1]: 'Risiko Sedang',
    sorted_clusters[2]: 'Risiko Tinggi'
}

df_merged['Tingkat_Kerentanan'] = df_merged['Cluster'].map(risk_mapping)
print("\nMapping of clusters to Risk Levels:")
for k, v in risk_mapping.items():
    print(f"  Cluster {k} -> {v}")

# Save cluster data
df_merged.to_csv(clean_csv_path, index=False)

# Visualizing the clusters (Poverty vs Dropout Rate, with size representing IPM)
plt.figure(figsize=(9, 7))
colors = {'Risiko Tinggi': '#d9534f', 'Risiko Sedang': '#f0ad4e', 'Risiko Rendah': '#5cb85c'}
sns.scatterplot(
    data=df_merged,
    x='Persentase_Miskin_Maret',
    y='Putus_Sekolah_per_10k_Penduduk',
    hue='Tingkat_Kerentanan',
    hue_order=['Risiko Tinggi', 'Risiko Sedang', 'Risiko Rendah'],
    palette=colors,
    size='IPM_2024',
    sizes=(40, 200),
    alpha=0.9,
    edgecolor='black',
    linewidth=0.8
)

plt.title("Kabupaten/Kota Clustering based on School Dropout Risk Vulnerability", fontsize=13, fontweight='bold', pad=15)
plt.xlabel("Persentase Penduduk Miskin (%)", fontsize=11, labelpad=10)
plt.ylabel("Angka Putus Sekolah per 10.000 Penduduk", fontsize=11, labelpad=10)
plt.legend(title='Tingkat Kerentanan & Capaian IPM', loc='upper right', bbox_to_anchor=(1, 1))

# Label each point on the scatter plot
for i, txt in enumerate(df_merged['Kab_Kota']):
    plt.annotate(txt.replace("Kab. ", "").replace("Kota ", ""), 
                 (df_merged.loc[i, 'Persentase_Miskin_Maret'], df_merged.loc[i, 'Putus_Sekolah_per_10k_Penduduk']),
                 textcoords="offset points", xytext=(0,5), ha='center', fontsize=8, color='#333333')

plt.tight_layout()
cluster_plot_path = os.path.join(plots_dir, "risk_clustering_scatter.png")
plt.savefig(cluster_plot_path, dpi=300)
plt.close()
print(f"Cluster plot saved to: {cluster_plot_path}")

# Generate Cluster summary stats
print("\n=== CLUSTER PROFILES ===")
summary = df_merged.groupby('Tingkat_Kerentanan')[cluster_features + ['Total_Putus_Sekolah']].mean()
print(summary)

# Generate list of members in each cluster
print("\n=== CLUSTER MEMBERSHIP ===")
for risk_level in ['Risiko Tinggi', 'Risiko Sedang', 'Risiko Rendah']:
    members = df_merged[df_merged['Tingkat_Kerentanan'] == risk_level]['Kab_Kota'].tolist()
    print(f"\n{risk_level} (Count = {len(members)}):")
    print(", ".join(members))

print("\n--- PHASE 5: REPORT TABLES GENERATION ---")
# 1. Condition table before and after scrubbing
print("Preparing Data Quality documentation...")
# We will save this as text details so it can be loaded in the notebook/report
dq_path = "plots/data_quality_report.txt"
with open(dq_path, "w") as f:
    f.write("=== DATA QUALITY REPORT: BEFORE VS AFTER SCRUBBING ===\n\n")
    f.write("1. Key Alignments:\n")
    f.write("   - IPM: Sliced rows 48-74. Replaced 'Kabupaten ' with 'Kab. ' to match keys.\n")
    f.write("   - Poverty: Sliced rows 0-26. Prefixed Kabupaten names with 'Kab. '.\n")
    f.write("   - Putus Sekolah: Sliced rows 5-31. Already had standard keys.\n")
    f.write("   - Joined: Inner join on standard 'Kab_Kota' key. Total rows = 27 (exactly matches Jabar administrative subdivisions).\n\n")
    f.write("2. Missing Value Resolution:\n")
    f.write("   - September poverty columns removed entirely due to 100% missing data at Kab/Kota level.\n")
    f.write("   - March poverty columns had 0 missing values.\n")
    f.write("   - Putus Sekolah NaN values filled with 0 (no NaN values were actually present in sliced range).\n")
    f.write("   - IPM 2024 and Laju IPM columns parsed to float successfully (0 missing values).\n\n")
    f.write("3. Outliers (IQR Method on Key Variables):\n")
    for col in ['Total_Putus_Sekolah', 'Persentase_Miskin_Maret', 'IPM_2024']:
        q1 = df_merged[col].quantile(0.25)
        q3 = df_merged[col].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outliers = df_merged[(df_merged[col] < lower_bound) | (df_merged[col] > upper_bound)]['Kab_Kota'].tolist()
        f.write(f"   - Variable '{col}':\n")
        f.write(f"     IQR = {iqr:.4f}, Lower Bound = {lower_bound:.4f}, Upper Bound = {upper_bound:.4f}\n")
        f.write(f"     Outlier regions: {outliers if outliers else 'None'}\n")

print(f"Data quality report written to: {dq_path}")
print("Pipeline finished successfully!")
