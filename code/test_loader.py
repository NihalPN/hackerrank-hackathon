from pathlib import Path

from data.loader import load_dataset


def main():
    dataset_dir = Path("dataset")

    dataset = load_dataset(dataset_dir)

    print("\n=== DATASET SANITY CHECK ===")

    print(f"Profiles:        {len(dataset.profiles)}")
    print(f"Events:          {len(dataset.events)}")
    print(f"Requests:        {len(dataset.requests)}")
    print(f"Payment options: {sum(len(x) for x in dataset.payment_options.values())}")
    print(f"Messages:        {sum(len(x) for x in dataset.messages.values())}")
    print(f"Images:          {len(dataset.images)}")

    print("\n=== SAMPLE PROFILE ===")
    user_id, profile = next(iter(dataset.profiles.items()))
    print("user_id:", user_id)
    print("currency:", profile.home_currency)
    print("balance:", profile.current_available_balance)
    print("minimum balance:", profile.minimum_balance_to_keep)

    print("\n=== SAMPLE REQUEST ===")
    request_id, request = next(iter(dataset.requests.items()))
    print("request_id:", request_id)
    print("user_id:", request.user_id)
    print("amount:", request.requested_amount)
    print("request date:", request.request_date)
    print("completion date:", request.desired_completion_date)

    print("\n=== PAYMENT OPTIONS FOR SAMPLE REQUEST ===")
    options = dataset.payment_options.get(request_id, [])

    for option in options:
        print(
            option.payment_method,
            "| payment:", option.payment_amount,
            "| payments:", option.number_of_payments,
            "| total:", option.total_payable_amount,
        )

    print("\n=== CHECKS ===")

    assert len(dataset.profiles) > 0
    assert len(dataset.events) > 0
    assert len(dataset.requests) > 0

    for request in dataset.requests.values():
        assert request.user_id in dataset.profiles, (
            f"Request {request.request_id} references missing "
            f"user {request.user_id}"
        )

    print("✓ Profiles loaded")
    print("✓ Events loaded")
    print("✓ Requests loaded")
    print("✓ Request → user relationships valid")
    print("✓ Loader sanity checks passed")

    print("\nEverything looks structurally healthy.")


if __name__ == "__main__":
    main()