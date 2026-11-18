"""
Balanced territory assignment for field technicians.

Assigns maintenance jobs to technicians so that every technician gets a similar
workload and a compact, nearby area. Uses synthetic jobs across Istanbul; the
original project used geocoded customer sites, which are not included here.

Run:  python balance.py
Out:  output/assignments.csv, output/territories.png, output/territories_map.html
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

N_JOBS = 600
N_TECHNICIANS = 15
SEED = 42
OUT = Path(__file__).parent / "output"

# Rough bounding boxes of populated Istanbul districts (lat_min, lat_max, lon_min, lon_max, weight)
AREAS = [
    (40.98, 41.08, 28.80, 28.95, 0.30),  # European side, west
    (41.03, 41.12, 28.95, 29.05, 0.30),  # European side, center/north
    (40.97, 41.03, 29.03, 29.15, 0.25),  # Asian side, Kadikoy/Atasehir
    (40.88, 40.95, 29.15, 29.30, 0.15),  # Asian side, Kartal/Pendik
]
PRIORITIES = ["Low", "Normal", "High", "Urgent"]


def synthetic_jobs(rng: np.random.Generator) -> pd.DataFrame:
    weights = np.array([a[4] for a in AREAS])
    area_idx = rng.choice(len(AREAS), size=N_JOBS, p=weights / weights.sum())
    lat = [rng.uniform(AREAS[i][0], AREAS[i][1]) for i in area_idx]
    lon = [rng.uniform(AREAS[i][2], AREAS[i][3]) for i in area_idx]
    return pd.DataFrame({
        "job_id": [f"J{n:04d}" for n in range(1, N_JOBS + 1)],
        "lat": lat,
        "lon": lon,
        "priority": rng.choice(PRIORITIES, size=N_JOBS, p=[0.3, 0.45, 0.18, 0.07]),
        "duration_h": rng.choice([0.5, 1, 1.5, 2, 3, 4], size=N_JOBS, p=[0.15, 0.3, 0.2, 0.2, 0.1, 0.05]),
    })


def capacity_assign(coords: np.ndarray, centers: np.ndarray, capacity: int) -> np.ndarray:
    """Assign each job to the nearest center that still has room (closest pairs first)."""
    dist = cdist(coords, centers)
    order = np.dstack(np.unravel_index(np.argsort(dist, axis=None), dist.shape))[0]
    tech = np.full(len(coords), -1)
    load = np.zeros(len(centers), dtype=int)
    for j, t in order:
        if tech[j] == -1 and load[t] < capacity:
            tech[j] = t
            load[t] += 1
    return tech


def assign(jobs: pd.DataFrame, rng: np.random.Generator, iterations: int = 15) -> pd.Series:
    """Capacity-constrained clustering: equal job counts per technician, compact territories.

    Like K-Means, but each technician can take at most ceil(jobs / technicians) jobs.
    Alternate between capacity-aware assignment and moving each center to its jobs' mean.
    """
    coords = jobs[["lat", "lon"]].to_numpy()
    capacity = int(np.ceil(len(coords) / N_TECHNICIANS))
    centers = coords[rng.choice(len(coords), N_TECHNICIANS, replace=False)].copy()
    for _ in range(iterations):
        tech = capacity_assign(coords, centers, capacity)
        centers = np.array([coords[tech == t].mean(axis=0) for t in range(N_TECHNICIANS)])
    return pd.Series(tech, index=jobs.index, name="technician")


def save_outputs(jobs: pd.DataFrame) -> None:
    OUT.mkdir(exist_ok=True)
    jobs.sort_values(["technician", "job_id"]).to_csv(OUT / "assignments.csv", index=False)

    summary = jobs.groupby("technician").agg(jobs=("job_id", "count"), hours=("duration_h", "sum"))
    print(summary.to_string())
    print(f"\nJobs per technician: min {summary.jobs.min()}, max {summary.jobs.max()}")

    fig, ax = plt.subplots(figsize=(9, 6))
    cmap = plt.get_cmap("tab20")
    for t, grp in jobs.groupby("technician"):
        ax.scatter(grp.lon, grp.lat, s=10, color=cmap(t % 20), label=f"T{t + 1}")
        ax.scatter(grp.lon.mean(), grp.lat.mean(), s=120, marker="X", color=cmap(t % 20), edgecolor="black")
    ax.set_title(f"{N_JOBS} jobs balanced across {N_TECHNICIANS} technicians (synthetic data)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(ncol=2, fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "territories.png", dpi=130)

    try:
        import folium
        m = folium.Map(location=[41.02, 29.02], zoom_start=11, tiles="cartodbpositron")
        colors = ["red", "blue", "green", "purple", "orange", "darkred", "cadetblue", "darkgreen",
                  "darkblue", "pink", "gray", "black", "lightred", "beige", "darkpurple"]
        for _, r in jobs.iterrows():
            folium.CircleMarker([r.lat, r.lon], radius=3, color=colors[r.technician % len(colors)],
                                fill=True, popup=f"{r.job_id} | T{r.technician + 1} | {r.priority}").add_to(m)
        m.save(OUT / "territories_map.html")
    except ImportError:
        print("folium not installed; skipping the interactive map")


def main() -> None:
    rng = np.random.default_rng(SEED)
    jobs = synthetic_jobs(rng)
    jobs["technician"] = assign(jobs, rng)
    save_outputs(jobs)


if __name__ == "__main__":
    main()
