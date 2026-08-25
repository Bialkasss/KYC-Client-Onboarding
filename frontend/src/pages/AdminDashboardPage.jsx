// Skeleton dashboard - placeholders only, no charting library wired up yet.
// Intended data sources once implemented: GET /api/onboarding/cases (case_status,
// client_status, ml_prediction, ml_approval_probability) aggregated client-side
// or via a future GET /api/admin/dashboard-metrics endpoint.
const PLACEHOLDER_CHARTS = [
  {
    title: 'Case volume by status',
    description: 'Open / Pending / Closed cases over time.',
  },
  {
    title: 'Client status breakdown',
    description: 'Pending / Active / Suspended / Rejected clients.',
  },
  {
    title: 'ML approval rate',
    description: 'Predicted APPROVED vs REJECTED rate across all cases.',
  },
  {
    title: 'Approval probability distribution',
    description: 'Histogram of ml_approval_probability across open cases.',
  },
  {
    title: 'Predicted vs actual outcome',
    description: 'ML prediction compared against final client status, once available.',
  },
  {
    title: 'Top rejection factors',
    description: 'Most frequent DiCE recommendation factors across rejected cases.',
  },
];

export default function AdminDashboardPage() {
  return (
    <div className="page">
      <h1>Dashboard</h1>
      <p className="hint">This page is a work-in-progress skeleton — charts are not wired up yet.</p>

      <div className="dashboard-grid">
        {PLACEHOLDER_CHARTS.map((chart) => (
          <section className="card dashboard-card" key={chart.title}>
            <h2>{chart.title}</h2>
            <p className="hint">{chart.description}</p>
            <div className="chart-placeholder">Chart coming soon</div>
          </section>
        ))}
      </div>
    </div>
  );
}
