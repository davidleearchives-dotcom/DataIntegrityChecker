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

def compare_excel_files(file_source, file_target, mapping_rules_str: str, progress_callback=None, source_include_dup: bool = False, target_include_dup: bool = False):
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
        
        # Identify Key Columns (Use ALL Mapped Columns as Composite Key)
        # Previously we used only the first column (generic_col_names[0])
        # Now we use ALL generic_col_names as the key for deduplication and merging
        key_cols = generic_col_names
        
        # Deduplicate based on ALL Mapped Columns with Normalization
        # User Requirement: Merge columns and remove spaces for robust key comparison
        if progress_callback: progress_callback(40, "Normalizing and removing duplicate keys...")
        
        def create_normalized_key(df, cols):
            # Create a temporary key column by joining all key columns
            # Logic: str(col).strip() for each col, then join
            return df[cols].astype(str).apply(lambda row: "".join([str(val).strip() for val in row]), axis=1)

        # Add normalized key column
        df_a_sub['__norm_key'] = create_normalized_key(df_a_sub, key_cols)
        df_b_sub['__norm_key'] = create_normalized_key(df_b_sub, key_cols)
        
        # Count duplicates for logging/debugging if needed, but here we just drop
        # Source Data (A): Keep only first occurrence UNLESS source_include_dup is True
        if not source_include_dup:
            df_a_sub = df_a_sub.drop_duplicates(subset=['__norm_key'], keep='first')
        
        # Target Data (B): Keep only first occurrence UNLESS target_include_dup is True
        # Note: Previous requirement was "DO NOT DROP DUPLICATES". 
        # But now we give user choice. If user says Exclude Duplicates, we drop.
        # If user says Include Duplicates (default behavior before was keep all), we keep.
        # Wait, previous default for Target was KEEP ALL.
        # But user complained about duplicates being counted.
        # So "Exclude Duplicates" means drop them.
        if not target_include_dup:
             df_b_sub = df_b_sub.drop_duplicates(subset=['__norm_key'], keep='first')
        
        # Merge on Normalized Key
        # how='right' -> Use Target Data as the base (Master).
        # If we have duplicates in B and we kept them, they will be preserved.
        # If we have duplicates in A and kept them, it might cause Cartesian product if B also has duplicates.
        # But that's what "Include Duplicates" implies - many-to-many match.
        
        if progress_callback: progress_callback(50, "Merging data (Target Base)...")
        
        # If both have duplicates, merge needs to handle it.
        # pd.merge on key handles many-to-many.
        merged = pd.merge(df_a_sub, df_b_sub, on='__norm_key', how='right', suffixes=('_A', '_B'), indicator=True)
        
        # Cleanup: Remove normalized key from result if desired, or keep hidden
        # The merge result will have __norm_key. We should not include it in the final output unless requested.
        # But we need to restore original column values?
        # The merged dataframe has columns: col_0_A, col_1_A..., col_0_B, col_1_B... AND __norm_key
        # Since we merged on __norm_key, the original key columns (generic_col_names) are NOT the join keys anymore.
        # So they WILL have _A and _B suffixes!
        # This changes the logic below significantly.
        
        # Remove the temporary column
        # merged.drop(columns=['__norm_key'], inplace=True) 
        
        # Update Key Cols variable to point to the normalized key?
        # No, we want to show original values.
        # But wait, if we merge on __norm_key, then `generic_col` will be present as `generic_col_A` and `generic_col_B`.
        # `generic_col` itself will NOT be in `merged` columns!
        
        # So we need to adjust the reconstruction logic.
        
        # Analyze Results
        
        # Remove the temporary column - No longer needed as we don't use occurrence
        # merged.drop(columns=['__occurrence'], inplace=True)
        
        # Analyze Results
        
        # Analyze Results
        if progress_callback: progress_callback(65, "Analyzing discrepancies...")
        
        # Initialize validation status
        merged['validation_status'] = 'Match'
        
        # Vectorized check for Missing
        # left_only: Source Only -> Should not happen in Right Join
        # right_only: Target Only -> Missing in Source (A)
        merged.loc[merged['_merge'] == 'right_only', 'validation_status'] = 'Missing_in_A'
        
        # For 'both', check mismatches
        both_mask = merged['_merge'] == 'both'
        mismatch_mask = pd.Series(False, index=merged.index)
        mismatch_details = pd.Series("", index=merged.index)
        
        for i, col in enumerate(generic_col_names):
            # Since we merged on __norm_key, ALL generic cols have suffixes _A and _B
            # if col in key_cols: continue -> NO, we want to check them too if they differ visually (but they matched on normalized key)
            
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
            
            # if col in key_cols:
                # This block is skipped by `if col in key_cols: continue` above.
                # So we are fine for the loop.
                # pass
            
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
            
            # Note: For key columns, even if normalized key matches, the visual value might differ (e.g. spaces)
            # We should probably flag this as mismatch?
            # User requirement: "숫자와 기호,특수문자를 다 합하여 비교해서 중복을 거르면"
            # This implies if "A 1" and "A1" match, they are SAME.
            # So we should NOT flag them as mismatch?
            # But here we are comparing row-by-row AFTER matching.
            # If we matched "A 1" with "A1", should we say "Match"? Yes.
            # So we should normalize here too?
            
            if col in key_cols:
                 val_a = val_a.str.replace(" ", "")
                 val_b = val_b.str.replace(" ", "")
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
            "source_rows": len(df_a_sub),
            "target_rows": len(df_b_sub),
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
            
            # Since we merged on __norm_key, ALL generic cols have suffixes _A and _B
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
            # key_val = row[key_col] # Now we have composite keys
            
            # Source Row Data
            src_row = {'type': 'Source', 'status': status}
            # Target Row Data
            tgt_row = {'type': 'Target', 'status': status}
            
            # Construct Key String for Display
            key_display_vals = []
            for k in key_cols:
                 key_display_vals.append(str(row.get(k, "")))
            src_row['key'] = " | ".join(key_display_vals)
            tgt_row['key'] = " | ".join(key_display_vals)
            
            for i, generic_col in enumerate(generic_col_names):
                col_display_name = source_cols_raw[i]
                
                # Special handling for Key Columns - Now they also have suffixes
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
