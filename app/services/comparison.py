import pandas as pd
import json
import re

def col2num(col_str):
    """
    Convert Excel column letter to 0-based index.
    A -> 0, B -> 1, AA -> 26, etc.
    """
    expn = 0
    col_num = 0
    for char in reversed(col_str):
        col_num += (ord(char.upper()) - ord('A') + 1) * (26 ** expn)
        expn += 1
    return col_num - 1

def compare_excel_files(file_source, file_target, mapping_rules_str: str):
    """
    Compares two excel files based on mapping rules using Column Letters (A, B, C...).
    Ignores the first row (header) for mapping, but preserves it for output.
    """
    try:
        mapping = json.loads(mapping_rules_str)
        source_cols_raw = mapping.get("source_cols", [])
        target_cols_raw = mapping.get("target_cols", [])
        
        # Convert Column Letters to Indices
        try:
            source_indices = [col2num(c.strip()) for c in source_cols_raw]
            target_indices = [col2num(c.strip()) for c in target_cols_raw]
        except Exception:
            raise ValueError("Invalid column format. Please use Excel column letters (e.g., A, B, C).")

        # Load Data
        # Support CSV and Excel
        # Check file extension or try both? 
        # file_source is a path string
        
        def load_file(path):
            if path.lower().endswith('.csv'):
                # Try reading csv. Assume utf-8, but could be cp949 for Korean
                try:
                    return pd.read_csv(path, encoding='utf-8')
                except UnicodeDecodeError:
                    return pd.read_csv(path, encoding='cp949')
            else:
                # Assume Excel
                return pd.read_excel(path)

        df_a = load_file(file_source)
        df_b = load_file(file_target)
        
        # Validate Column Bounds
        max_col_a = df_a.shape[1]
        max_col_b = df_b.shape[1]
        
        invalid_a = [source_cols_raw[i] for i, idx in enumerate(source_indices) if idx >= max_col_a]
        invalid_b = [target_cols_raw[i] for i, idx in enumerate(target_indices) if idx >= max_col_b]
        
        if invalid_a or invalid_b:
            raise ValueError(f"Columns out of range: Source={invalid_a}, Target={invalid_b}")
            
        # Select relevant columns by Index
        # We rename them to internal generic names (col_0, col_1...) to facilitate merge
        generic_col_names = [f"__col_{i}" for i in range(len(source_indices))]
        
        df_a_sub = df_a.iloc[:, source_indices].copy()
        df_b_sub = df_b.iloc[:, target_indices].copy()
        
        # Assign generic names for merging
        df_a_sub.columns = generic_col_names
        df_b_sub.columns = generic_col_names
        
        # Identify Key Column (First column in the list)
        key_col = generic_col_names[0]
        
        # Merge
        merged = pd.merge(df_a_sub, df_b_sub, on=key_col, how='outer', suffixes=('_A', '_B'), indicator=True)
        
        # Analyze Results
        summary = {
            "total_rows": len(merged),
            "matched": 0,
            "mismatched": 0,
            "missing_source": 0, # In B but not A
            "missing_target": 0  # In A but not B
        }

        def determine_status(row):
            if row['_merge'] == 'left_only':
                return 'Missing_in_B'
            elif row['_merge'] == 'right_only':
                return 'Missing_in_A'
            else:
                # Compare other columns
                is_match = True
                mismatch_indices = [] # Store original column letters? or generic index?
                
                for i, col in enumerate(generic_col_names):
                    if col == key_col: continue
                    val_a = row.get(f"{col}_A")
                    val_b = row.get(f"{col}_B")
                    
                    # Handle NaN
                    if pd.isna(val_a) and pd.isna(val_b):
                        continue
                        
                    # Loose comparison (str vs int, strip, etc.)?
                    # Strict for now as per previous logic, but ensure type compatibility if needed
                    if str(val_a).strip() != str(val_b).strip(): # Basic string normalization
                        is_match = False
                        # We want to report the Original Column Letter of Source
                        mismatch_indices.append(source_cols_raw[i])
                
                if is_match:
                    return 'Match'
                else:
                    return f"Mismatch: {', '.join(mismatch_indices)}"

        merged['validation_status'] = merged.apply(determine_status, axis=1)
        
        # Update Summary
        summary["matched"] = len(merged[merged['validation_status'] == 'Match'])
        summary["mismatched"] = len(merged[merged['validation_status'].str.startswith('Mismatch')])
        summary["missing_target"] = len(merged[merged['validation_status'] == 'Missing_in_B']) 
        summary["missing_source"] = len(merged[merged['validation_status'] == 'Missing_in_A'])
        
        # Reconstruct Result DataFrame
        # We need to attach the result to the original df_a rows.
        # But since we merged on a Key that might be duplicated or complex, we need to map back carefully.
        # We used the KEY VALUE from the specified column.
        
        # 1. Create a map of Key -> Status from merged result
        # Note: If Key is not unique, this might be ambiguous. Assuming Key is unique for now.
        status_map = merged.set_index(key_col)['validation_status'].to_dict()
        
        # 2. Get the Key Column Name in Original DF_A
        # key_col_idx = source_indices[0]
        # key_col_name_a = df_a.columns[key_col_idx]
        
        # Actually, let's just use the merged result logic as before, but adapted for indices.
        
        processed_data = []
        
        # Helper: Get original column name for key
        key_idx_a = source_indices[0]
        key_idx_b = target_indices[0]
        
        # For lookup
        # We can't easily set index on a column by integer position in pandas without name.
        # So we use the column name at that position.
        col_name_key_a = df_a.columns[key_idx_a]
        col_name_key_b = df_b.columns[key_idx_b]
        
        df_a_idx = df_a.set_index(col_name_key_a)
        df_b_idx = df_b.set_index(col_name_key_b)
        
        for idx, row in merged.iterrows():
            key_val = row[key_col]
            status = row['validation_status']
            
            row_data = {}
            
            if status == 'Missing_in_A':
                # Fetch from B
                if key_val in df_b_idx.index:
                    b_data = df_b_idx.loc[key_val]
                    if isinstance(b_data, pd.DataFrame): b_data = b_data.iloc[0]
                    
                    # We try to fill A's columns. 
                    # If we know the mapping (A->B), we can fill mapped columns.
                    # Unmapped columns in A will be empty.
                    
                    # Fill Key
                    row_data[col_name_key_a] = key_val
                    
                    # Fill Mapped Columns
                    for src_i, tgt_i in zip(source_indices, target_indices):
                        if src_i == key_idx_a: continue
                        src_col_name = df_a.columns[src_i]
                        tgt_col_name = df_b.columns[tgt_i]
                        row_data[src_col_name] = b_data.get(tgt_col_name)
                        
            elif status == 'Missing_in_B':
                # Fetch from A
                if key_val in df_a_idx.index:
                    a_data = df_a_idx.loc[key_val]
                    if isinstance(a_data, pd.DataFrame): a_data = a_data.iloc[0]
                    row_data = a_data.to_dict()
                    row_data[col_name_key_a] = key_val
            
            else: # Match or Mismatch
                # Fetch from A
                if key_val in df_a_idx.index:
                    a_data = df_a_idx.loc[key_val]
                    if isinstance(a_data, pd.DataFrame): a_data = a_data.iloc[0]
                    row_data = a_data.to_dict()
                    row_data[col_name_key_a] = key_val
            
            row_data['Verification_Result'] = status
            processed_data.append(row_data)

        result_df = pd.DataFrame(processed_data)
        
        # Filter Result DF to show ONLY Mapped Columns + Verification Result
        # Get column names for mapped source indices
        display_cols = [df_a.columns[i] for i in source_indices]
        # Ensure Key Column is included (it usually is in source_indices)
        
        final_cols = display_cols + ['Verification_Result']
        
        # Ensure result_df contains these columns
        # (It should, because we filled them from A or B)
        result_df = result_df[final_cols]
        
        # Prepare Preview Data (Source/Target pairs) for Mismatches
        # This is separate from result_df (which is for Excel export)
        preview_data = []
        
        for idx, row in merged.iterrows():
            status = row['validation_status']
            if status == 'Match':
                continue
                
            key_val = row[key_col]
            
            # Source Row Data
            src_row = {'type': 'Source', 'key': key_val, 'status': status}
            # Target Row Data
            tgt_row = {'type': 'Target', 'key': key_val, 'status': status}
            
            # Fill columns
            # Also fill the Key Column explicitly, because it might not be in the loop if we skipped it
            # But we need to display it if it's part of the mapped columns.
            
            for i, generic_col in enumerate(generic_col_names):
                col_display_name = df_a.columns[source_indices[i]] # Use Source Header Name
                
                # Special handling for Key Column
                if generic_col == key_col:
                    val_a = key_val
                    val_b = key_val
                else:
                    val_a = row.get(f"{generic_col}_A")
                    val_b = row.get(f"{generic_col}_B")
                
                # Format None/NaN
                if pd.isna(val_a): val_a = ""
                if pd.isna(val_b): val_b = ""
                
                src_row[col_display_name] = val_a
                tgt_row[col_display_name] = val_b
            
            preview_data.append(src_row)
            preview_data.append(tgt_row)

        return summary, result_df, preview_data

    except Exception as e:
        print(f"Error in comparison: {str(e)}")
        raise e
