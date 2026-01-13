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

def compare_excel_files(file_source, file_target, mapping_rules_str: str, progress_callback=None):
    """
    Compares two excel files based on mapping rules using Column Letters (A, B, C...).
    Ignores the first row (header) for mapping, but preserves it for output.
    """
    try:
        if progress_callback: progress_callback(5, "Initializing comparison...")

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
            if path.lower().endswith(('.csv', '.txt')):
                # Try reading csv. Assume utf-8, but could be cp949 for Korean
                # Force all columns to be string to avoid type mismatch issues
                try:
                    return pd.read_csv(path, encoding='utf-8', dtype=str)
                except UnicodeDecodeError:
                    return pd.read_csv(path, encoding='cp949', dtype=str)
            else:
                # Assume Excel
                return pd.read_excel(path, dtype=str)

        if progress_callback: progress_callback(10, "Loading source file...")
        df_a = load_file(file_source)
        if progress_callback: progress_callback(25, "Loading target file...")
        df_b = load_file(file_target)
        
        # Fill NaN with empty string to avoid matching issues
        df_a = df_a.fillna("")
        df_b = df_b.fillna("")
        
        # Trim whitespace from ALL string columns
        # This is expensive but necessary for robust matching
        if progress_callback: progress_callback(30, "Normalizing data...")
        df_a = df_a.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        df_b = df_b.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        
        # Validate Column Bounds
        max_col_a = df_a.shape[1]
        max_col_b = df_b.shape[1]
        
        invalid_a = [source_cols_raw[i] for i, idx in enumerate(source_indices) if idx >= max_col_a]
        invalid_b = [target_cols_raw[i] for i, idx in enumerate(target_indices) if idx >= max_col_b]
        
        if invalid_a or invalid_b:
            raise ValueError(f"Columns out of range: Source={invalid_a}, Target={invalid_b}")
            
        # Select relevant columns by Index
        # We rename them to internal generic names (col_0, col_1...) to facilitate merge
        if progress_callback: progress_callback(35, "Processing columns...")
        generic_col_names = [f"__col_{i}" for i in range(len(source_indices))]
        
        # Ensure generic_col_names length matches source_indices
        if len(generic_col_names) != len(source_indices):
            # This should logically not happen unless range is weird
            pass

        # Check if generic_col_names matches dataframe columns count? No.
        # We are assigning NEW names.
        
        df_a_sub = df_a.iloc[:, source_indices].copy()
        df_b_sub = df_b.iloc[:, target_indices].copy()
        
        # Assign generic names for merging
        # Critical: Ensure number of columns matches
        if len(df_a_sub.columns) != len(generic_col_names):
             raise ValueError(f"Source column count mismatch. Expected {len(generic_col_names)}, got {len(df_a_sub.columns)}")
        if len(df_b_sub.columns) != len(generic_col_names):
             raise ValueError(f"Target column count mismatch. Expected {len(generic_col_names)}, got {len(df_b_sub.columns)}")

        df_a_sub.columns = generic_col_names
        df_b_sub.columns = generic_col_names
        
        # Identify Key Column (First column in the list)
        key_col = generic_col_names[0]
        
        # Enforce Unique Key Constraint
        # User feedback: "Why only 40 rows?" -> Because we dropped duplicates.
        # User wants to compare ALL rows even if keys are duplicated.
        # Solution: Use 'cumcount' to match duplicates sequentially (1st with 1st, 2nd with 2nd)
        # instead of dropping them or allowing Cartesian explosion.
        
        if progress_callback: progress_callback(40, "Handling duplicate keys...")
        
        # Add a temporary occurrence column for merging
        df_a_sub['__occurrence'] = df_a_sub.groupby(key_col).cumcount()
        df_b_sub['__occurrence'] = df_b_sub.groupby(key_col).cumcount()
        
        # Merge on Key AND Occurrence
        if progress_callback: progress_callback(50, "Merging data...")
        merged = pd.merge(df_a_sub, df_b_sub, on=[key_col, '__occurrence'], how='outer', suffixes=('_A', '_B'), indicator=True)
        
        # Remove the temporary column
        merged.drop(columns=['__occurrence'], inplace=True)
        
        # Analyze Results
        
        # Analyze Results
        if progress_callback: progress_callback(65, "Analyzing discrepancies...")
        
        # Initialize validation status
        merged['validation_status'] = 'Match'
        
        # Vectorized check for Missing
        merged.loc[merged['_merge'] == 'left_only', 'validation_status'] = 'Missing_in_B'
        merged.loc[merged['_merge'] == 'right_only', 'validation_status'] = 'Missing_in_A'
        
        # For 'both', check mismatches
        both_mask = merged['_merge'] == 'both'
        mismatch_mask = pd.Series(False, index=merged.index)
        mismatch_details = pd.Series("", index=merged.index)
        
        for i, col in enumerate(generic_col_names):
            if col == key_col: continue
            
            # Compare columns (vectorized)
            # Ensure string conversion for safe comparison
            val_a = merged.loc[both_mask, f"{col}_A"].astype(str).str.strip()
            val_b = merged.loc[both_mask, f"{col}_B"].astype(str).str.strip()
            
            # Replace 'nan' string with empty if needed, or rely on pandas equality
            # Let's handle NaN explicitly if needed, but astype(str) makes NaN 'nan'
            # If both are 'nan', they match.
            
            # Fix: Handle potential Key Error if col is not in merged?
            # merged was created with suffixes _A and _B.
            # generic_col_names includes key_col.
            # key_col in merged does NOT have suffix if it was the join key?
            # Wait, pd.merge on=key_col...
            # If suffixes are provided, non-key columns get suffixes.
            # THE KEY COLUMN usually does NOT get suffix if it's the join key.
            # But here generic_col_names has ALL columns including key.
            # So for key_col, f"{col}_A" might not exist!
            
            if col == key_col:
                # This block is skipped by `if col == key_col: continue` above.
                # So we are fine for the loop.
                pass
            
            # Double check column existence
            col_a_name = f"{col}_A"
            col_b_name = f"{col}_B"
            
            if col_a_name not in merged.columns:
                # Fallback: maybe it didn't get suffix?
                # But we forced suffixes.
                # If a column was unique to one side? No, we renamed both sides to same generic names.
                # So they collide and MUST get suffixes.
                raise ValueError(f"Missing column in merged data: {col_a_name}")
                
            val_a = merged.loc[both_mask, col_a_name].astype(str).str.strip()
            val_b = merged.loc[both_mask, col_b_name].astype(str).str.strip()
            
            col_mismatch = val_a != val_b
            
            if col_mismatch.any():
                # Update global mismatch mask
                mismatch_mask.loc[col_mismatch[col_mismatch].index] = True
                
                # Append column name to details
                # This part is slightly slower but much faster than row iteration
                # We only operate on mismatched rows for this column
                original_col_name = source_cols_raw[i]
                mismatch_details.loc[col_mismatch[col_mismatch].index] += f"{original_col_name}, "

        # Update status for mismatches
        final_mismatch_mask = both_mask & mismatch_mask
        if final_mismatch_mask.any():
            merged.loc[final_mismatch_mask, 'validation_status'] = "Mismatch: " + mismatch_details.loc[final_mismatch_mask].str.rstrip(", ")
        
        # Update Summary
        if progress_callback: progress_callback(80, "Summarizing results...")
        summary = {
            "total_rows": len(merged),
            "matched": len(merged[merged['validation_status'] == 'Match']),
            "mismatched": len(merged[merged['validation_status'].str.startswith('Mismatch')]),
            "missing_target": len(merged[merged['validation_status'] == 'Missing_in_B']),
            "missing_source": len(merged[merged['validation_status'] == 'Missing_in_A'])
        }
        
        # Reconstruct Result DataFrame
        # We need to attach the result to the original df_a rows.
        # But since we merged on a Key that might be duplicated or complex, we need to map back carefully.
        # We used the KEY VALUE from the specified column.
        
        if progress_callback: progress_callback(90, "Preparing result file...")
        
        # Reconstruct Result DataFrame using vectorized operations
        result_df = pd.DataFrame(index=merged.index)
        
        # Mask for "Use B" (when Missing in A)
        use_b_mask = merged['validation_status'] == 'Missing_in_A'
        
        for i, generic_col in enumerate(generic_col_names):
            original_name = source_cols_raw[i]
            
            # If Key Column, it doesn't have suffix if it's the join key
            if generic_col == key_col:
                # Key column is just the column itself, no suffix
                combined = merged[generic_col]
            else:
                vals_a = merged[f"{generic_col}_A"]
                vals_b = merged[f"{generic_col}_B"]
                # Combine: where use_b_mask is True, take B, else A
                combined = vals_a.where(~use_b_mask, vals_b)
            
            result_df[original_name] = combined
            
        # Add Verification Result
        result_df['Verification_Result'] = merged['validation_status']
        
        # Prepare Preview Data (Source/Target pairs) for Mismatches
        # This part iterates only over mismatches, which should be much fewer than total rows.
        # If everything is mismatch, it might be slow, but usually < 100% mismatch.
        # We only need top 200 for preview in the route, but here we return all?
        # Route says: preview_list[:200].
        # So we should limit generation here to avoid memory/time waste?
        # The return signature implies full list.
        # But if we have 30k mismatches, creating 60k row dicts is slow.
        # Let's optimize: only generate top 200 preview items here?
        # OR: Return the dataframe of mismatches and let the route handle it?
        # Current contract: returns preview_data list.
        # Let's limit it to 200 items (100 mismatches) right here for performance.
        
        preview_data = []
        
        mismatch_rows = merged[merged['validation_status'] != 'Match'].head(100) # Limit to 100 discrepancies
        
        for idx, row in mismatch_rows.iterrows():
            status = row['validation_status']
            key_val = row[key_col]
            
            # Source Row Data
            src_row = {'type': 'Source', 'key': key_val, 'status': status}
            # Target Row Data
            tgt_row = {'type': 'Target', 'key': key_val, 'status': status}
            
            for i, generic_col in enumerate(generic_col_names):
                col_display_name = source_cols_raw[i]
                
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

        if progress_callback: progress_callback(95, "Finalizing...")
        return summary, result_df, preview_data

    except Exception as e:
        print(f"Error in comparison: {str(e)}")
        raise e
