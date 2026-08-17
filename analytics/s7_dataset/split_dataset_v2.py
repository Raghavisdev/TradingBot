import os
import pandas as pd

def split_dataset():
    base_dir = os.path.dirname(__file__)
    csv_path = os.path.join(base_dir, 's7_training_dataset_v2.csv')
    
    if not os.path.exists(csv_path):
        print("Dataset not found. Run build_dataset_v2.py first.")
        return
        
    df = pd.read_csv(csv_path)
    
    # 1. Filter resolved signals only
    if 'label_resolved' in df.columns:
        df_resolved = df[df['label_resolved'] == 1].copy()
    else:
        df_resolved = df.dropna(subset=['Y_2x', 'Y_5x', 'Y_10x', 'Y_rug']).copy()
        
    print(f"Total rows: {len(df)}")
    print(f"Resolved rows: {len(df_resolved)}")
    
    # 2. Sort chronologically
    df_resolved = df_resolved.sort_values(by='t0_timestamp')
    
    # 3. Split 60/20/20
    n = len(df_resolved)
    if n == 0:
        print("No resolved signals to split.")
        return
        
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    
    train_df = df_resolved.iloc[:train_end]
    val_df = df_resolved.iloc[train_end:val_end]
    test_df = df_resolved.iloc[val_end:]
    
    train_df.to_csv(os.path.join(base_dir, 's7_train.csv'), index=False)
    val_df.to_csv(os.path.join(base_dir, 's7_validation.csv'), index=False)
    test_df.to_csv(os.path.join(base_dir, 's7_test.csv'), index=False)
    
    print(f"Train rows: {len(train_df)}")
    print(f"Val rows: {len(val_df)}")
    print(f"Test rows: {len(test_df)}")

if __name__ == "__main__":
    split_dataset()
