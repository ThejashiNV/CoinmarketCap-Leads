import pandas as pd

df = pd.read_csv("output/final_leads.csv")
df.to_excel("output/final_leads.xlsx", index=False)

print("Excel file created successfully!")