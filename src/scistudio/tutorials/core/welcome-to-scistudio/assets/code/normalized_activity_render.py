def render(collection):
    """Plot normalized activity by condition.

    A plot script receives the collection bound to one block output port and
    returns a matplotlib figure. Nothing here is written to disk by hand: the
    figure the function returns is what the plot card shows.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    df = collection.items.open_one()
    order = ["neg_control", "treated_1uM", "treated_5uM", "pos_control"]
    labels = {
        "neg_control": "Neg control",
        "treated_1uM": "1 uM treated",
        "treated_5uM": "5 uM treated",
        "pos_control": "Pos control",
    }
    present = [condition for condition in order if condition in set(df["condition"])]
    grouped = df.groupby("condition")["normalized_activity"]
    means = grouped.mean().reindex(present)
    std = grouped.std().reindex(present).fillna(0)

    x = np.arange(len(present))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(x, means.to_numpy(), yerr=std.to_numpy(), capsize=4, color="#2d7891", alpha=0.82)

    for idx, condition in enumerate(present):
        values = df.loc[df["condition"] == condition, "normalized_activity"].to_numpy()
        jitter = np.linspace(-0.09, 0.09, len(values)) if len(values) > 1 else np.array([0.0])
        ax.scatter(idx + jitter, values, color="#1c211b", s=24, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([labels[condition] for condition in present], rotation=15, ha="right")
    ax.set_ylabel("Normalized activity")
    ax.set_title("Normalized cell activity")
    # The two control levels the normalisation pins: 0 is the negative
    # control, 1 is the positive control. Every bar is read against them.
    ax.axhline(0, color="#78716c", linewidth=0.8)
    ax.axhline(1, color="#78716c", linewidth=0.8, linestyle="--")
    fig.tight_layout()
    return fig
