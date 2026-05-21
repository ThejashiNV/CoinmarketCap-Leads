from src.extractors.extract_emails import run_email_extraction
import pandas as pd


def generate_leads():
    # Run email extraction
    run_email_extraction()

    # Load final output
    df = pd.read_csv("output/final_leads.csv")

    # Remove duplicate projects
    df = df.drop_duplicates(subset=["CoinMarketCap URL"])

    # Remove rows with no website and no email
    df = df[
        ~(
            (df["Official Website URL"] == "N/A") &
            (df["Official Email ID"] == "N/A")
        )
    ]

    # Save cleaned CSV
    df.to_csv("output/final_leads.csv", index=False)

    # Save Excel file
    df.to_excel("output/final_leads.xlsx", index=False)

    print("Saved cleaned output to:")
    print(" - output/final_leads.csv")
    print(" - output/final_leads.xlsx")


if __name__ == "__main__":
    generate_leads()