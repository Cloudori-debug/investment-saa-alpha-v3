"""CSS snippet for hold/exit edition only."""


def hold_exit_edition_css() -> str:
    return """
.he-edition-banner {
  border: 1px solid #7b93ab;
  background: #eef3f8;
  border-radius: 8px;
  padding: 0.55rem 0.75rem;
  margin: 0 0 0.65rem;
  font-size: 0.92rem;
  font-weight: 700;
  line-height: 1.35;
  color: #1a334d;
}
.he-edition-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.35rem;
}
.he-edition-chip {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.16rem 0.42rem;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #c5d0db;
  color: #3d5266;
}
.he-month-board {
  border: 1px solid #b7a88a;
  border-radius: 8px;
  background: #faf7f1;
  padding: 0.65rem 0.8rem 0.7rem;
  margin: 0 0 0.75rem;
}
.he-month-kicker {
  font-weight: 800;
  font-size: 0.95rem;
  margin-bottom: 0.25rem;
  letter-spacing: -0.02em;
}
.he-month-note {
  font-size: 0.78rem;
  line-height: 1.4;
  margin: 0 0 0.55rem;
  color: #5c5346;
}
.he-month-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.4rem;
}
@media (min-width: 720px) {
  .he-month-grid { grid-template-columns: 1fr 1fr; }
}
.he-month-card {
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #fff;
  padding: 0.5rem 0.6rem 0.55rem;
}
.he-month-hot {
  border-color: #e8a0a0;
  background: #fff5f5;
}
.he-month-warn {
  border-color: #e0c48a;
  background: #fffbf2;
}
.he-month-muted {
  border-color: #d4d4d4;
  background: #fafafa;
}
.he-month-card-h {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.4rem;
  margin-bottom: 0.3rem;
}
.he-month-title {
  font-weight: 700;
  font-size: 0.8rem;
  color: #3d3d3d;
}
.he-month-count {
  font-weight: 800;
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
  color: #64748b;
}
.he-month-chips {
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
}
.he-month-chip {
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  padding: 0.28rem 0.35rem;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.03);
}
.he-month-name {
  font-size: 0.82rem;
  font-weight: 700;
}
.he-month-why {
  font-size: 0.74rem;
  color: #64748b;
  line-height: 1.35;
}
.he-month-empty {
  font-size: 0.78rem;
  color: #94a3b8;
}
.he-ops-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem 0.5rem;
  margin-top: 0.4rem;
  padding-top: 0.35rem;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}
.he-ops-cell {
  min-width: 0;
}
.he-ops-k {
  display: block;
  font-size: 0.7rem;
  font-weight: 700;
  color: #64748b;
  letter-spacing: 0.02em;
  margin-bottom: 0.08rem;
}
.he-ops-v {
  display: block;
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.35;
}
.he-ops-d {
  display: block;
  font-size: 0.74rem;
  font-weight: 500;
  line-height: 1.35;
  opacity: 0.92;
  margin-top: 0.08rem;
}
.he-quality-board {
  border: 1px solid #6a8a72;
  border-radius: 8px;
  background: #eef5ee;
  padding: 0.65rem 0.8rem 0.55rem;
  margin: 0 0 0.75rem;
}
.he-quality-kicker {
  font-weight: 800;
  font-size: 1rem;
  letter-spacing: -0.02em;
  margin-bottom: 0.2rem;
  color: #1c3324;
}
.he-quality-note {
  font-size: 0.8rem;
  line-height: 1.4;
  margin: 0 0 0.45rem;
  color: #3d5a45;
}
.he-quality-empty {
  font-size: 0.84rem;
  color: #64748b;
}
.he-quality-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.he-quality-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.55rem;
  padding: 0.35rem 0;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  font-size: 0.9rem;
}
.he-quality-rank {
  flex: 0 0 1.4rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: #64748b;
}
.he-quality-name {
  flex: 1 1 auto;
  min-width: 8rem;
}
.he-quality-meta {
  flex: 1 1 100%;
  font-size: 0.8rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #2d4a3c;
  margin-left: 1.95rem;
}
.he-quality-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 0.28rem;
  margin: 0.2rem 0 0.4rem;
}
.he-quality-chip {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  padding: 0.14rem 0.4rem;
  border-radius: 4px;
  background: #e8f0ea;
  color: #2d4a3c;
  border: 1px solid #c5d6c9;
}
.he-quality-chip-rank {
  background: #eef1f4;
  color: #64748b;
  border-color: #d0d7de;
}
"""
