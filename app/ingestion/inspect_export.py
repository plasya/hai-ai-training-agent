# inspect_export.py
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
import sys

EXPORT_XML = Path("../../data/raw/apple_health_export/export.xml")  # adjust path if needed

def count_record_and_workout_types(xml_path, top_n=50):
    # Try a streaming parse (memory-friendly) that counts <Record> and <Workout> attributes.
    rec_counter = Counter()
    workout_counter = Counter()
    total_records = 0
    total_workouts = 0

    # iterparse yields events; we can clear elements to save memory
    context = ET.iterparse(str(xml_path), events=("end",))
    for event, elem in context:
        tag = elem.tag
        if tag == "Record":
            total_records += 1
            t = elem.attrib.get("type") or elem.attrib.get("unit") or "<unknown>"
            rec_counter[t] += 1
            # clear element
            elem.clear()
        elif tag == "Workout":
            total_workouts += 1
            wt = elem.attrib.get("workoutActivityType") or "<unknown>"
            workout_counter[wt] += 1
            elem.clear()
        # optional: clear parent references to help memory (no-op for simple ET)
    return total_records, rec_counter, total_workouts, workout_counter

def print_counts(total_records, rec_counter, total_workouts, workout_counter, top_n=50):
    print(f"Total Record elements: {total_records}")
    print("Top Record types:")
    for typ, cnt in rec_counter.most_common(top_n):
        print(f"  {typ}: {cnt}")
    print()
    print(f"Total Workout elements: {total_workouts}")
    print("Workout activity types (counts):")
    for wt, cnt in workout_counter.most_common():
        print(f"  {wt}: {cnt}")

if __name__ == "__main__":
    xml_path = EXPORT_XML
    if not xml_path.exists():
        print("ERROR: export.xml not found at", xml_path, file=sys.stderr)
        sys.exit(1)
    totals = count_record_and_workout_types(xml_path)
    print_counts(*totals)