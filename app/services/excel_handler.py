from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import pandas as pd

def generate_styled_excel(df: pd.DataFrame, output_path: str):
    """
    Generates a styled Excel file from the dataframe.
    Highlights rows based on 'Verification_Result' column.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Verification Result"
    
    # Styles
    # Light Red for Mismatch (Wait, PRD says: "Light Red for Mismatch" in Preview Table, 
    # but "Yellow" for Cell in Excel?
    # PRD 64: "대조본(B)과 비교하여 값이 다른 셀(Cell)은 배경색을 'Yellow'로"
    # PRD 65: "대조본(B)과 비교하여 누락된 열 데이터는 원본파일(A)에 배경색을 'Red'로"
    
    yellow_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    red_fill = PatternFill(start_color="FFCCCC", end_color="FFCCCC", fill_type="solid")
    
    # Write Header
    headers = list(df.columns)
    ws.append(headers)
    
    # Write Data
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=False), start=2):
        ws.append(row)
        
        # Apply Styles
        # Get Verification Result (Last Column)
        result_col_idx = len(headers) # 1-based index
        result_cell = ws.cell(row=r_idx, column=result_col_idx)
        result_val = result_cell.value
        
        if not result_val:
            continue
            
        if str(result_val).startswith("Mismatch"):
            # Highlight SPECIFIC Mismatched Cells if possible, or the whole row?
            # PRD: "값이 다른 셀(Cell)은 배경색을 'Yellow'" -> Cell level.
            # My comparison logic returned "Mismatch: ColA, ColB". I can parse this.
            
            # Highlight row indicator?
            # Let's highlight the Result cell at least.
            
            mismatched_cols_str = str(result_val).replace("Mismatch: ", "")
            mismatched_cols = [c.strip() for c in mismatched_cols_str.split(",")]
            
            for col_name in mismatched_cols:
                try:
                    col_idx = headers.index(col_name) + 1
                    ws.cell(row=r_idx, column=col_idx).fill = yellow_fill
                except ValueError:
                    pass # Column might not exist in result if hidden
                    
        elif result_val == "Missing_in_B":
            # Highlight entire row Red?
            # PRD: "누락된 열 데이터는... 배경색을 'Red'"
            for c_idx in range(1, len(headers) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = red_fill
                
        elif result_val == "Missing_in_A":
            # Highlight entire row Red (or distinct color?)
            # I'll use Red as well for "Missing" concept.
            for c_idx in range(1, len(headers) + 1):
                ws.cell(row=r_idx, column=c_idx).fill = red_fill

    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column = [cell for cell in column]
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        ws.column_dimensions[column[0].column_letter].width = adjusted_width

    wb.save(output_path)
    return output_path
