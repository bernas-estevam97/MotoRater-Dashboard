"""Canonical column renaming mappings and data formatting helpers for MotoRater."""

import pandas as pd

# Standardized column name normalization map
# Cleans units and formats coordinates, angles, and accelerations
column_rename_map = {
    # Lengths, Widths, Heights, and Clearances
    "Step Width (Hind)": "Step Width (Hind) (m)",
    "Step Width (Front)": "Step Width (Front) (m)",
    "Step Length (Left)": "Step Length (Left) (m)",
    "Step Length (Right)": "Step Length (Right) (m)",
    "Toe Clearance Forepaw (Right)": "Toe Clearance Forepaw (Right) (m)",
    "Toe Clearance Hindpaw (Right)": "Toe Clearance Hindpaw (Right) (m)",
    "Toe Clearance Forepaw (Left)": "Toe Clearance Forepaw (Left) (m)",
    "Toe Clearance Hindpaw (Left)": "Toe Clearance Hindpaw (Left) (m)",
    "Iliac Crest Height (Right)": "Iliac Crest Height (Right) (m)",
    "Iliac Crest Height (Left)": "Iliac Crest Height (Left) (m)",
    "Hip Height (Right)": "Hip Height (Right) (m)",
    "Hip Height (Left)": "Hip Height (Left) (m)",
    "Tail Base Height (Right)": "Tail Base Height (Right) (m)",
    "Tail Base Height (Left)": "Tail Base Height (Left) (m)",
    "Nose Height": "Nose Height (m)",
    "Tail Tip Height": "Tail Tip Height (m)",
    "Shoulder Height (Right)": "Shoulder Height (Right) (m)",
    "Shoulder Height (Left)": "Shoulder Height (Left) (m)",

    # Protraction/Retraction = Euclidean distance hind toe -> PSIS (a length, not an angle)
    "Protraction/Retraction (Right)": "Protraction/Retraction (Right) (m)",
    "Protraction/Retraction (Left)": "Protraction/Retraction (Left) (m)",

    # Angles
    "Hip Angle (Right)": "Hip Angle (Right) (º)",
    "Knee Angle (Right)": "Knee Angle (Right) (º)",
    "Hip Angle (Left)": "Hip Angle (Left) (º)",
    "Knee Angle (Left)": "Knee Angle (Left) (º)",
    "Tail Angle (Side View)": "Tail Angle (Side View) (º)",

    # Accelerations (Cleaning up the squared symbol)
    "Front Right Ax (m/s^2)": "Front Right Ax (m/s²)",
    "Front Right Ay (m/s^2)": "Front Right Ay (m/s²)",
    "Front Right |Acc| (m/s^2)": "Front Right |Acc| (m/s²)",
    "Front Left Ax (m/s^2)": "Front Left Ax (m/s²)",
    "Front Left Ay (m/s^2)": "Front Left Ay (m/s²)",
    "Front Left |Acc| (m/s^2)": "Front Left |Acc| (m/s²)",
    "Hind Right Ax (m/s^2)": "Hind Right Ax (m/s²)",
    "Hind Right Ay (m/s^2)": "Hind Right Ay (m/s²)",
    "Hind Right |Acc| (m/s^2)": "Hind Right |Acc| (m/s²)",
    "Hind Left Ax (m/s^2)": "Hind Left Ax (m/s²)",
    "Hind Left Ay (m/s^2)": "Hind Left Ay (m/s²)",
    "Hind Left |Acc| (m/s^2)": "Hind Left |Acc| (m/s²)"
}


def get_column_rename_map() -> dict:
    """Returns a copy of the canonical column renaming map."""
    return column_rename_map.copy()


def trim_footer(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the summary block that the filtering scripts write under the Kinematics frames
    (blank row, 'Time Duration', Mean/Std/Median/Min/Max/Max_Normalized_Mean/CV, 'Height Window').
    Those rows carry a label instead of a number in 'Time', so keeping numeric-Time rows works for
    v1 (9 footer rows) and v2 (10) files and is a no-op on already-trimmed data. Text columns that
    become fully numeric are converted."""
    if 'Time' not in df.columns:
        return df
    t = pd.to_numeric(df['Time'], errors='coerce')
    if t.notna().all():
        return df
    out = df[t.notna()].copy()
    for col in out.select_dtypes(include=['object']).columns:
        try:
            out[col] = pd.to_numeric(out[col])
        except (ValueError, TypeError):
            pass
    return out


def format_pval(x) -> str:
    """Format a p-value float with scientific precision."""
    if pd.isna(x):
        return "NaN"
    try:
        val = float(x)
        return f"{val:.4f}" if val > 0.0001 else "<0.0001"
    except (ValueError, TypeError):
        return str(x)


if __name__ == "__main__":
    # Self-check: v2 footer (blank, Time Duration, 7 stats, Height Window) is removed, data kept, idempotent.
    frames = pd.DataFrame({'Time': [0.0, 0.01, 0.02], 'Hip Height (Left)': [1.0, 2.0, 3.0]})
    labels = ['Time Duration', 'Mean', 'Std', 'Median', 'Min', 'Max', 'Max_Normalized_Mean', 'CV',
              'Height Window (start, end s)']
    footer = pd.DataFrame({'Time': [None] + labels, 'Hip Height (Left)': [None] + [9.0] * len(labels)})
    raw = pd.concat([frames, footer], ignore_index=True).astype(object)
    out = trim_footer(raw)
    assert len(out) == 3 and out['Time'].dtype.kind == 'f', out
    assert trim_footer(out) is out
    print("data_mappings self-check passed")
