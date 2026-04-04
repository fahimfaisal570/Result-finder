import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.getcwd())
import database as db

profile_name = "eee 09"
exam_id = "1234"

def get_performance_archetypes(df_pivot, n_clusters=4):
    if df_pivot.empty: return None
    data = df_pivot.dropna().copy()
    if len(data) < n_clusters: return None

    # Feature Engineering: Mean (Strength) and Variance (Consistency)
    features = pd.DataFrame(index=data.index)
    features['mean_gp'] = data.mean(axis=1)
    features['std_gp'] = data.std(axis=1).fillna(0)

    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(scaled_data)

    features['Cluster'] = clusters
    centroids = features.groupby('Cluster').mean()

    mapping = {}
    if len(centroids) == 4:
        sorted_by_mean = centroids.sort_values(by='mean_gp', ascending=False)
        top_tier    = sorted_by_mean.iloc[:2]
        bottom_tier = sorted_by_mean.iloc[2:]

        # Among top: high variance = Specialist
        if top_tier.iloc[0]['std_gp'] > top_tier.iloc[1]['std_gp']:
            specialist_id     = top_tier.index[0]
            consistent_high_id = top_tier.index[1]
        else:
            specialist_id     = top_tier.index[1]
            consistent_high_id = top_tier.index[0]

        # Among bottom: higher mean = Average, lower = Struggling
        average_id   = bottom_tier.index[0]
        struggling_id = bottom_tier.index[1]

        mapping = {
            consistent_high_id: 'Consistent High',
            specialist_id:      'Specialist (High Variance)',
            average_id:         'Medium / Average',
            struggling_id:      'Struggling / Below Avg'
        }
    else:
        mapping = {c: f"Cluster {c}" for c in centroids.index}

    features['Archetype'] = features['Cluster'].map(mapping)
    return features

# Load data
df_sub_raw = pd.DataFrame(db.get_subject_data_for_exam(profile_name, exam_id))

if df_sub_raw.empty:
    print("No subject data found.")
    sys.exit()

# Pivot
df_pivot = df_sub_raw.pivot_table(index='reg_no', columns='subject_code', values='gp', aggfunc='first')

# 1. Correlation Analysis
print("--- Correlation Analysis ---")
corr_matrix = df_pivot.corr()
if 'EEE 2202' in corr_matrix.index and 'EEE 2204' in corr_matrix.columns:
    print(f"Correlation between EEE 2202 and EEE 2204: {corr_matrix.loc['EEE 2202', 'EEE 2204']:.2f}")
else:
    # Try finding similar names
    print("Exact codes EEE 2202/2204 not found in correlation matrix. Available codes:")
    print(corr_matrix.index.tolist())

# Inspect the raw grades for some students for these two subjects
if 'EEE 2202' in df_pivot.columns and 'EEE 2204' in df_pivot.columns:
    print("\nGrades for EEE 2202 vs EEE 2204 (first 10 students):")
    print(df_pivot[['EEE 2202', 'EEE 2204']].head(10))

# 2. Clustering Analysis
print("\n--- Clustering Analysis ---")
features = get_performance_archetypes(df_pivot)
if features is not None:
    print("Archetype Counts:")
    print(features['Archetype'].value_counts())
    
    print("\nSpecialist Cluster Details (First 5):")
    specialists = features[features['Archetype'] == 'Specialist (High Variance)']
    print(specialists.head(5))
    
    # Check centroids
    print("\nCluster Centroids (Mean GP, Std GP):")
    print(features.groupby('Archetype')[['mean_gp', 'std_gp']].mean())
    
    # Why is Specialist so high? Check if many students have high variance.
    print("\nVariance Distribution in Top Tier:")
    # Re-identify IDs as in the logic
    data = df_pivot.dropna().copy()
    f = pd.DataFrame(index=data.index)
    f['mean_gp'] = data.mean(axis=1)
    f['std_gp'] = data.std(axis=1).fillna(0)
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(f)
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    clusters = kmeans.fit_predict(scaled_data)
    f['Cluster'] = clusters
    centroids = f.groupby('Cluster').mean()
    sorted_by_mean = centroids.sort_values(by='mean_gp', ascending=False)
    top_tier_indices = sorted_by_mean.iloc[:2].index.tolist()
    
    top_tier_students = f[f['Cluster'].isin(top_tier_indices)]
    print(f"Total Top Tier Students: {len(top_tier_students)}")
    print(top_tier_students.groupby('Cluster')[['mean_gp', 'std_gp']].mean())
else:
    print("Clustering failed (not enough data).")
