import pandas as pd
import json

def compare_excel_files(file_source, file_target, mapping_rules_str: str):
    """
    Compares two excel files based on mapping rules.
    mapping_rules: JSON string like {"source_cols": ["A", "B"], "target_cols": ["A", "B"], "key_col_index": 0}
    
    Returns:
        summary: dict
        result_df: DataFrame (ready for styling)
    """
    try:
        mapping = json.loads(mapping_rules_str)
        source_cols = mapping.get("source_cols", [])
        target_cols = mapping.get("target_cols", [])
        
        # Determine Key Column (default to first column if not specified)
        # We assume the user selects columns in order, and the first one is the ID.
        # If no columns specified, use all intersection? No, strict to PRD.
        
        # Load Data
        df_a = pd.read_excel(file_source)
        df_b = pd.read_excel(file_target)
        
        # Validate columns exist
        missing_cols_a = [c for c in source_cols if c not in df_a.columns]
        missing_cols_b = [c for c in target_cols if c not in df_b.columns]
        
        if missing_cols_a or missing_cols_b:
            raise ValueError(f"Missing columns: Source={missing_cols_a}, Target={missing_cols_b}")
            
        # Normalize column names for comparison
        # We will rename target columns to match source columns for the merge
        rename_map = dict(zip(target_cols, source_cols))
        df_b_renamed = df_b.rename(columns=rename_map)
        
        # Select only relevant columns for comparison
        df_a_sub = df_a[source_cols].copy()
        df_b_sub = df_b_renamed[source_cols].copy()
        
        # Identify Key Column (Assume first column in list is the unique key)
        key_col = source_cols[0]
        
        # Merge
        # indicator=True adds '_merge' column: 'left_only', 'right_only', 'both'
        merged = pd.merge(df_a_sub, df_b_sub, on=key_col, how='outer', suffixes=('_A', '_B'), indicator=True)
        
        # Analyze Results
        results = []
        
        summary = {
            "total_rows": len(merged),
            "matched": 0,
            "mismatched": 0,
            "missing_source": 0, # In B but not A
            "missing_target": 0  # In A but not B
        }

        # We need to construct the final output dataframe based on df_a structure
        # PRD: "Original File(A) shape maintained... missing rows from B marked... missing rows from A marked"
        
        # Actually, if it's Missing in A (exists in B only), we should append it?
        # PRD says: "Missing in A: In Target(B) but not Source(A)"
        # "Missing in B: In Source(A) but not Target(B)"
        # "Result file: Maintain Source(A) shape... Missing in B marked Red... "
        # Does it imply we should ADD rows for "Missing in A"?
        # "대조본(B)과 비교하여 누락된 열 데이터는 원본파일(A)에 배경색을 'Red'로 해서 생성한다음'누락'으로 표시해줘."
        # This sentence is slightly ambiguous. "누락된 열 데이터" (missing column data? or row?). Context suggests Rows.
        # If it's missing in B (exists in A), we mark A's row Red? 
        # Usually "Missing in B" means B doesn't have it. So A has it. It's an "orphan" in A.
        # "Missing in A" means A doesn't have it. We probably need to append these rows to the report to show them?
        # PRD: "Missing_in_B: Source(A) has it, Target(B) missing." -> Highlight Red in A?
        # PRD: "Mismatch: One of columns diff" -> Highlight Yellow.
        
        # Let's process row by row or vectorized.
        
        # Vectorized approach for status:
        # 1. missing_target (left_only) -> Exists in A, not B.
        # 2. missing_source (right_only) -> Exists in B, not A.
        # 3. both -> Check values.
        
        def determine_status(row):
            if row['_merge'] == 'left_only':
                return 'Missing_in_B'
            elif row['_merge'] == 'right_only':
                return 'Missing_in_A'
            else:
                # Compare other columns
                is_match = True
                mismatch_cols = []
                for col in source_cols:
                    if col == key_col: continue
                    val_a = row.get(f"{col}_A")
                    val_b = row.get(f"{col}_B")
                    
                    # Handle NaN comparison
                    if pd.isna(val_a) and pd.isna(val_b):
                        continue
                    if val_a != val_b:
                        is_match = False
                        mismatch_cols.append(col)
                
                if is_match:
                    return 'Match'
                else:
                    return f"Mismatch: {', '.join(mismatch_cols)}"

        merged['validation_status'] = merged.apply(determine_status, axis=1)
        
        # Update Summary
        summary["matched"] = len(merged[merged['validation_status'] == 'Match'])
        summary["mismatched"] = len(merged[merged['validation_status'].str.startswith('Mismatch')])
        summary["missing_target"] = len(merged[merged['validation_status'] == 'Missing_in_B']) # In A only
        summary["missing_source"] = len(merged[merged['validation_status'] == 'Missing_in_A']) # In B only
        
        # Prepare Result DataFrame
        # We want to show Source Data primarily, but include Target data for Mismatches?
        # PRD: "Original File(A) shape maintained... add 'Verification Result' column"
        # If we only maintain A shape, we lose "Missing in A" (rows only in B).
        # But usually a verification report should show ALL discrepancies.
        # I will include ALL rows from the Outer Join.
        
        # Construct final DF
        # We need to reconstruct the original columns of A. 
        # Since we did an outer join on a SUBSET of columns, we might have lost other columns of A if we didn't include them in merge?
        # To preserve A's full context, we should merge the result back to full df_a?
        # But `merged` has all IDs.
        
        # Better approach:
        # 1. Use `merged` (which contains key + comparison cols) as the base for status.
        # 2. Join `merged[['key', 'validation_status']]` back to `df_a` (left join) to keep A's shape.
        # 3. For 'Missing in A' (rows in B only), we should append them to the bottom?
        # PRD says "Maintain Source(A) shape". This strictly implies ONLY rows in A?
        # But then "Missing in A" (In B but not A) wouldn't be shown. 
        # However, usually "Verification Tool" needs to show what's missing.
        # I will append "Missing in A" rows at the bottom, filling A-specific columns with NaN/Info.
        
        # Let's rebuild the result.
        final_rows = []
        
        # Helper to find original row in df_a or df_b
        # This is slow for large files. Optimized approach:
        
        # 1. Set index to key_col for fast lookup
        df_a_idx = df_a.set_index(key_col)
        df_b_idx = df_b.set_index(key_col) # Note: df_b uses original column names
        
        # Iterate over merged to build result
        # merged has key_col.
        
        processed_data = []
        
        for idx, row in merged.iterrows():
            key_val = row[key_col]
            status = row['validation_status']
            
            row_data = {}
            
            if status == 'Missing_in_A':
                # Get data from B
                # We need to map B columns to A columns where possible
                # For non-mapped columns, leave empty?
                if key_val in df_b_idx.index:
                    # Handle duplicate keys? Assume unique for now.
                    # df_b_idx.loc[key_val] might return Series or DataFrame
                    b_data = df_b_idx.loc[key_val]
                    if isinstance(b_data, pd.DataFrame): b_data = b_data.iloc[0]
                    
                    # Fill A columns from B if mapped
                    row_data[key_col] = key_val
                    for src, tgt in zip(source_cols, target_cols):
                        if src == key_col: continue
                        row_data[src] = b_data.get(tgt)
            
            elif status == 'Missing_in_B':
                # Get data from A
                if key_val in df_a_idx.index:
                    a_data = df_a_idx.loc[key_val]
                    if isinstance(a_data, pd.DataFrame): a_data = a_data.iloc[0]
                    row_data = a_data.to_dict()
                    row_data[key_col] = key_val # Ensure key is present
            
            else: # Match or Mismatch
                # Get data from A (Primary)
                if key_val in df_a_idx.index:
                    a_data = df_a_idx.loc[key_val]
                    if isinstance(a_data, pd.DataFrame): a_data = a_data.iloc[0]
                    row_data = a_data.to_dict()
                    row_data[key_col] = key_val
            
            row_data['Verification_Result'] = status
            processed_data.append(row_data)
            
        result_df = pd.DataFrame(processed_data)
        
        # Ensure columns order matches A + Result
        final_cols = list(df_a.columns) + ['Verification_Result']
        # Add any columns that might be missing if we added rows from B (should fit into A's schema)
        result_df = result_df.reindex(columns=final_cols)
        
        return summary, result_df

    except Exception as e:
        print(f"Error in comparison: {str(e)}")
        raise e
