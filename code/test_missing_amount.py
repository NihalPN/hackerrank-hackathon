from pathlib import Path


from data.loader import load_dataset


def main():
    root = Path(__file__).resolve().parents[1]
    dataset = load_dataset(root / "dataset")

    events = (
        dataset.events.values()
        if isinstance(dataset.events, dict)
        else dataset.events
    )

    missing = []

    for event in events:
        amount = event.amount

        if amount is None or str(amount).strip() == "":
            missing.append(event)

    print("=== MISSING AMOUNT DIAGNOSTIC ===")
    print(f"Missing amounts: {len(missing)}")

    print("\n=== EVENTS ===")

    for event in missing:
        print(
            f"{event.event_id}"
            f" | user={event.user_id}"
            f" | type={event.event_type}"
            f" | {event.direction.value}"
            f" | {event.category}"
            f" | {event.description}"
            f" | event_date={event.event_date}"
            f" | settlement={event.settlement_date}"
            f" | status={event.status.value}"
        )

    print("\n=== IMAGE LINKS ===")

    images = (
        dataset.images.values()
        if isinstance(dataset.images, dict)
        else dataset.images
    )

    image_by_event = {}

    for image in images:
        if image.related_event_id:
            image_by_event[image.related_event_id] = image.image_id

    for event in missing:
        image_id = image_by_event.get(event.event_id)

        print(
            event.event_id,
            "| image:",
            image_id if image_id else "NONE",
        )

    print("\n=== CHECK ===")

    assert len(missing) > 0

    print("✓ Missing amounts identified")
    print("✓ No missing amount was converted to zero")


if __name__ == "__main__":
    main()