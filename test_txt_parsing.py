import pandas as pd
import io

# Sample content mimicking the user's image
csv_content = """"이력번호","전송일자","의료기관코드","의료기관명"
30879,2026-01-12 23:56:36.000,"11100338","서울성모병원"
30878,2026-01-12 23:56:25.000,"11100338","서울성모병원"
"""

# Write to a .txt file
with open("test_data.txt", "w", encoding="utf-8") as f:
    f.write(csv_content)

# Try reading it with pandas
try:
    df = pd.read_csv("test_data.txt", encoding="utf-8")
    print("Successfully read .txt file:")
    print(df)
except Exception as e:
    print(f"Error reading .txt file: {e}")
