from datetime import datetime
import traceback

from src.extractors.extract_categories import extract_categories
from src.extractors.extract_projects import extract_projects_from_category
from src.extractors.extract_project_details import extract_project_details
from src.collectors.generate_leads import generate_leads


def run_step(step_name, func):
    print("\n" + "=" * 60)
    print(f"Starting: {step_name}")
    print("=" * 60)

    start_time = datetime.now()

    try:
        func()
        end_time = datetime.now()
        print(f"\nCompleted: {step_name} in {end_time - start_time}")

    except Exception as e:
        print(f"\nFailed: {step_name}")
        print(f"Error: {e}")
        traceback.print_exc()
        raise


def main():
    print("\nMASTER PIPELINE STARTED\n")

    run_step("Extract Categories", extract_categories)
    run_step("Extract Projects", extract_projects_from_category)
    run_step("Extract Project Details", extract_project_details)
    run_step("Generate Final Leads", generate_leads)

    print("\nMASTER PIPELINE COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    main()