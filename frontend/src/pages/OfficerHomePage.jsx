import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { api } from '../api/api';
import CaseFilters, { matchesDueDateFilter, sortCasesByDueDate } from '../components/CaseFilters';

const DUE_SOON_DAYS = 30;

function statusRowClass(status) {
  if (status === 'OPEN') return 'row-open';
  if (status === 'PENDING') return 'row-pending';
  if (status === 'CLOSED') return 'row-closed';
  return '';
}

function dueDateClass(dueDate, status) {
  if (!dueDate || status === 'CLOSED') return '';
  const daysLeft = Math.ceil((new Date(dueDate) - new Date()) / (1000 * 60 * 60 * 24));
  return daysLeft <= DUE_SOON_DAYS ? 'due-date-soon' : '';
}

function dateOnly(value) {
  return value ? value.split(/[ T]/)[0] : '—';
}

export default function OfficerHomePage() {
  const { user } = useAuth();
  const [cases, setCases] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedStatuses, setSelectedStatuses] = useState([]);
  const [selectedClientStatuses, setSelectedClientStatuses] = useState([]);
  const [dueDateFilter, setDueDateFilter] = useState('all');
  const [dueDateSort, setDueDateSort] = useState('none');
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCases, setTotalCases] = useState(0);
  const ITEMS_PER_PAGE = 50;

  const loadCases = useCallback((page = 0) => {
    if (!user?.entityId) {
      console.log('User not available, skipping load');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    const offset = page * ITEMS_PER_PAGE;
    
    // Multiple selected statuses are OR'd together server-side via comma-separated list
    const statusFilter = selectedStatuses.length > 0 ? selectedStatuses : undefined;

    console.log('Loading cases:', { statusFilter, entityId: user.entityId, offset, limit: ITEMS_PER_PAGE });

    // Always request with pagination parameters to get the paginated response format
    api
      .getCases(statusFilter, user.entityId, ITEMS_PER_PAGE, offset)
      .then((response) => {
        console.log('API Response:', response, 'type:', typeof response);
        // Should now always be in paginated format: {total, offset, limit, cases: [...]}
        if (response && typeof response === 'object' && 'cases' in response) {
          const casesList = Array.isArray(response.cases) ? response.cases : [];
          const total = typeof response.total === 'number' ? response.total : 0;
          console.log('Setting cases:', casesList.length, 'total:', total);
          setCases(casesList);
          setTotalCases(total);
          setCurrentPage(page);
        } else {
          console.error('Response missing cases property:', response);
          setError('Invalid response format: missing cases array');
        }
      })
      .catch((err) => {
        console.error('API Error:', err);
        setError(err.message || 'Failed to load cases');
      })
      .finally(() => setLoading(false));
  }, [user?.entityId, selectedStatuses]);

  // Load first page on mount or when user changes
  useEffect(() => {
    loadCases(0);
  }, [loadCases]);

  if (loading) return <div className="page">Loading your cases...</div>;
  if (error) return <div className="page error">Error: {error}</div>;
  if (!user?.entityId) return <div className="page">Not authenticated</div>;

  const toggleStatus = (status) => {
    setSelectedStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status]
    );
  };

  const toggleClientStatus = (status) => {
    setSelectedClientStatuses((prev) =>
      prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status]
    );
  };

  // Filter locally for client status and date (since we can't send multiple filters to backend for now)
  // In a production app, you'd want to support multiple filter combinations on the backend
  const visibleCases = sortCasesByDueDate(
    cases.filter(
      (c) =>
        (selectedClientStatuses.length === 0 || selectedClientStatuses.includes(c.client_status)) &&
        matchesDueDateFilter(c.due_date, dueDateFilter, c.case_status)
    ),
    dueDateSort
  );

  const totalPages = Math.max(1, Math.ceil(totalCases / ITEMS_PER_PAGE));
  const startIndex = totalCases === 0 ? 0 : currentPage * ITEMS_PER_PAGE + 1;
  const endIndex = Math.min((currentPage + 1) * ITEMS_PER_PAGE, totalCases);

  return (
    <div className="page">
      <h1>My Cases</h1>

      <CaseFilters
        selectedStatuses={selectedStatuses}
        onToggleStatus={toggleStatus}
        selectedClientStatuses={selectedClientStatuses}
        onToggleClientStatus={toggleClientStatus}
        dueDateFilter={dueDateFilter}
        onDueDateFilterChange={setDueDateFilter}
        dueDateSort={dueDateSort}
        onDueDateSortChange={setDueDateSort}
      />

      {totalCases === 0 ? (
        <p>No cases are currently assigned to you.</p>
      ) : (
        <>
          <div className="pagination-info">
            Showing {startIndex}–{endIndex} of {totalCases} cases
          </div>
          <table className="cases-table">
            <thead>
              <tr>
                <th>Case ID</th>
                <th>Client</th>
                <th>Product</th>
                <th>Case Status</th>
                <th>Client Status</th>
                <th>Due Date</th>
                <th>Case Opened</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visibleCases.length === 0 && (
                <tr>
                  <td colSpan={8}>No cases match the selected filters.</td>
                </tr>
              )}
              {visibleCases.map((c) => (
                <tr key={c.case_id} className={statusRowClass(c.case_status)}>
                  <td>{c.case_id}</td>
                  <td className="client-name">{c.client_name}</td>
                  <td>{c.product_type}</td>
                  <td>
                    <span className={`status-badge status-${c.case_status.toLowerCase()}`}>
                      {c.case_status}
                    </span>
                  </td>
                  <td>
                    <span className={`status-badge status-${c.client_status.toLowerCase()}`}>
                      {c.client_status}
                    </span>
                  </td>
                <td className={dueDateClass(c.due_date, c.case_status)}>{c.due_date || '—'}</td>
                <td>{dateOnly(c.opened_date)}</td>
                <td>
                  <Link to={`/cases/${c.case_id}`} className="view-case-button">View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="pagination-controls">
          <button 
            onClick={() => loadCases(currentPage - 1)} 
            disabled={currentPage === 0}
            className="button-secondary"
          >
            ← Previous
          </button>
          
          <div className="pagination-pages">
            {Array.from({ length: totalPages }, (_, i) => (
              <button
                key={i}
                onClick={() => loadCases(i)}
                className={currentPage === i ? 'active' : ''}
                style={{
                  fontWeight: currentPage === i ? 'bold' : 'normal',
                  textDecoration: currentPage === i ? 'underline' : 'none'
                }}
              >
                {i + 1}
              </button>
            )).slice(Math.max(0, currentPage - 2), Math.min(totalPages, currentPage + 3))}
          </div>
          
          <button 
            onClick={() => loadCases(currentPage + 1)} 
            disabled={currentPage >= totalPages - 1}
            className="button-secondary"
          >
            Next →
          </button>
        </div>
      </>
      )}
    </div>
  );
}