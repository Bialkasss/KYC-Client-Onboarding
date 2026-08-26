import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/api';
import AssignOfficerModal from '../components/AssignOfficerModal';
import OpenCaseModal from '../components/OpenCaseModal';
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

export default function AdminHomePage() {
  const [cases, setCases] = useState([]);
  const [officers, setOfficers] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [assignError, setAssignError] = useState(null);
  const [activeCase, setActiveCase] = useState(null);
  const [selectedStatuses, setSelectedStatuses] = useState([]);
  const [selectedClientStatuses, setSelectedClientStatuses] = useState([]);
  const [dueDateFilter, setDueDateFilter] = useState('all');
  const [dueDateSort, setDueDateSort] = useState('none');
  const [showOpenCaseModal, setShowOpenCaseModal] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalCases, setTotalCases] = useState(0);
  const ITEMS_PER_PAGE = 50;

  const loadCases = useCallback((page = 0) => {
    if (!officers || officers.length === 0) {
      console.log('Officers not loaded yet, skipping');
      return;
    }

    setLoading(true);
    setError(null);
    const offset = page * ITEMS_PER_PAGE;
    
    // Multiple selected statuses are OR'd together server-side via comma-separated list
    const statusFilter = selectedStatuses.length > 0 ? selectedStatuses : undefined;

    console.log('Loading admin cases:', { statusFilter, offset, limit: ITEMS_PER_PAGE });

    api
      .getCases(statusFilter, undefined, ITEMS_PER_PAGE, offset)
      .then((response) => {
        console.log('Cases API Response:', response);
        // Handle paginated response format
        if (response && typeof response === 'object' && 'cases' in response) {
          const casesList = Array.isArray(response.cases) ? response.cases : [];
          const total = typeof response.total === 'number' ? response.total : 0;
          setCases(casesList);
          setTotalCases(total);
          setCurrentPage(page);
        } else {
          console.error('Unexpected response format:', response);
          setError('Unexpected response format');
        }
      })
      .catch((err) => {
        console.error('API Error:', err);
        setError(err.message || 'Failed to load cases');
      })
      .finally(() => setLoading(false));
  }, [selectedStatuses, ITEMS_PER_PAGE, officers.length]);

  // Load officers on mount
  useEffect(() => {
    let cancelled = false;

    api.getOfficers()
      .then((allOfficers) => {
        if (!cancelled) {
          setOfficers(allOfficers);
        }
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, []);

  // Load cases when officers are ready
  useEffect(() => {
    if (officers.length > 0) {
      loadCases(0);
    }
  }, [officers.length, loadCases]);

  // Reload when status filter changes
  useEffect(() => {
    loadCases(0);
  }, [selectedStatuses, loadCases]);

  const handleAssignOfficer = async (caseId, officerId) => {
    setAssignError(null);
    try {
      const result = await api.assignOfficer(caseId, officerId);
      setCases((prev) =>
        prev.map((c) =>
          c.case_id === caseId
            ? { ...c, assigned_officer_id: result.assigned_officer_id, officer_name: result.officer_name }
            : c
        )
      );
    } catch (err) {
      setAssignError(err.message);
      return false;
    }
  };

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

  const handleCaseOpened = () => {
    loadCases(currentPage);
  };

  // Filter visible cases for display
  const visibleCases = useMemo(
    () =>
      sortCasesByDueDate(
        cases.filter(
          (c) =>
            (selectedClientStatuses.length === 0 || selectedClientStatuses.includes(c.client_status)) &&
            matchesDueDateFilter(c.due_date, dueDateFilter, c.case_status)
        ),
        dueDateSort
      ),
    [cases, selectedClientStatuses, dueDateFilter, dueDateSort]
  );

  const totalPages = Math.max(1, Math.ceil(totalCases / ITEMS_PER_PAGE));

  if (loading) return <div className="page">Loading cases...</div>;
  if (error) return <div className="page error">Error: {error}</div>;

  const pageStart = currentPage * ITEMS_PER_PAGE + 1;
  const pageEnd = Math.min((currentPage + 1) * ITEMS_PER_PAGE, totalCases);

  return (
    <div className="page">
      <h1>All Cases</h1>
      {assignError && <p className="error">{assignError}</p>}

      <button type="button" className="open-case-button" onClick={() => setShowOpenCaseModal(true)}>
        + Open a New Case
      </button>

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

      <div className="pagination-info">
        Showing {pageStart}–{pageEnd} of {totalCases} cases
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
            <th>Assigned Officer</th>
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
              <td>
                <button type="button" className="button-secondary" onClick={() => setActiveCase(c)}>
                  {c.officer_name || 'Unassigned'}
                </button>
              </td>
              <td>
                <Link to={`/cases/${c.case_id}`} className="view-case-button">View Case</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="pagination-controls">
        <button
          type="button"
          className="button-secondary"
          disabled={currentPage === 0}
          onClick={() => loadCases(currentPage - 1)}
        >
          ← Previous
        </button>

        <div className="pagination-pages">
          {Array.from({ length: totalPages }, (_, i) => {
            const start = Math.max(0, currentPage - 2);
            const end = Math.min(totalPages, currentPage + 3);
            if (i < start || i >= end) return null;
            return (
              <button
                key={i}
                type="button"
                className={`pagination-page ${i === currentPage ? 'active' : ''}`}
                onClick={() => loadCases(i)}
              >
                {i + 1}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          className="button-secondary"
          disabled={currentPage >= totalPages - 1}
          onClick={() => loadCases(currentPage + 1)}
        >
          Next →
        </button>
      </div>

      {activeCase && (
        <AssignOfficerModal
          caseItem={activeCase}
          officers={officers}
          onClose={() => setActiveCase(null)}
          onAssigned={handleAssignOfficer}
        />
      )}

      {showOpenCaseModal && (
        <OpenCaseModal
          officers={officers}
          onClose={() => setShowOpenCaseModal(false)}
          onOpened={handleCaseOpened}
        />
      )}
    </div>
  );
}
