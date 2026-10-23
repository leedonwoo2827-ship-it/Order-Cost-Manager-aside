import React, { useState, useMemo, useEffect } from 'react';
import { IntegratedDataRow } from '../types';
import {
  Download,
  Filter,
  Search,
  AlertTriangle,
  CheckCircle2,
  Edit2,
  Save,
  DollarSign,
  Calendar,
  Layers,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  CheckSquare,
  Square,
  RefreshCw,
  Maximize2,
  FileText,
} from 'lucide-react';
import { ReceiptExportModal } from './ReceiptExportModal';
import { RpaRunModal } from './RpaRunModal';
import { groupReceiptRows, isReceiptEligible } from '../utils/receiptDocument';
import { buildCostClaimPayload, isCostClaimTarget, roundKey } from '../utils/costClaim';

interface DataSheetViewProps {
  data: IntegratedDataRow[];
  onUpdateRow: (updatedRow: IntegratedDataRow) => void;
  onExportExcel: () => void;
  onNavigateToMappings: () => void;
  onRefreshSharedFolder?: () => Promise<void>;
  onConnectDirectory?: () => void;
  isRefreshing?: boolean;
  lastSyncTime?: string | null;
  onShowToast?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

export const DataSheetView: React.FC<DataSheetViewProps> = ({
  data,
  onUpdateRow,
  onExportExcel,
  onNavigateToMappings,
  onRefreshSharedFolder,
  onConnectDirectory,
  isRefreshing = false,
  lastSyncTime,
  onShowToast,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'need_review' | 'partial' | 'combined' | 'unmapped' | 'normal'>('all');
  const [selectedMonth, setSelectedMonth] = useState<string>('all');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editFormData, setEditFormData] = useState<Partial<IntegratedDataRow>>({});
  const [sortField, setSortField] = useState<keyof IntegratedDataRow>('id');
  const [sortAsc, setSortAsc] = useState(true);
  const [receiptModalOpen, setReceiptModalOpen] = useState(false);
  const [claimBusy, setClaimBusy] = useState(false);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [rpaStatus, setRpaStatus] = useState<Record<string, string>>({});

  // 자동입력 상태 열: 엔진이 켜져 있으면 회차별 정리·올리기 결과를 가져온다
  useEffect(() => {
    if (!window.rpaApi) return undefined;
    let alive = true;
    const load = async () => {
      if (document.hidden) return;
      const res = await window.rpaApi!.call({ path: '/api/state' });
      if (!alive || !res.ok || !res.data?.rounds) return;
      const next: Record<string, string> = {};
      for (const r of res.data.rounds as { 과정명: string; 회차: string; 정리: string; 올리기: string }[]) {
        next[roundKey(String(r.과정명), r.회차)] = r.올리기 && r.올리기 !== '미실행' ? r.올리기 : r.정리;
      }
      setRpaStatus(next);
    };
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const rpaBadge = (status: string | undefined) => {
    if (!status) return <span className="text-slate-300">-</span>;
    const tone =
      status === '성공' ? 'bg-emerald-100 text-emerald-800'
      : status === '준비완료' ? 'bg-sky-100 text-sky-800'
      : status === '증빙누락' ? 'bg-rose-100 text-rose-700'
      : ['실패', '오류', '중단'].includes(status) ? 'bg-red-100 text-red-700'
      : 'bg-indigo-100 text-indigo-800';
    return <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${tone}`}>{status}</span>;
  };
  const [initialReceiptGroupKey, setInitialReceiptGroupKey] = useState<string | null>(null);

  const receiptGroups = useMemo(() => groupReceiptRows(data), [data]);

  // 청구월 목록 추출
  const availableMonths = useMemo(() => {
    const months = new Set<string>();
    data.forEach((r) => {
      if (r.claimMonth) months.add(r.claimMonth);
    });
    return Array.from(months);
  }, [data]);

  // 통계 계산
  const stats = useMemo(() => {
    const totalCount = data.length;
    const totalCost = data.reduce((acc, cur) => acc + (Number(cur.totalCost) || 0), 0);
    const totalGovSubsidy = data.reduce((acc, cur) => acc + (Number(cur.govSubsidy) || 0), 0);
    
    const partialCount = data.filter((r) => r.note.includes('부분입금')).length;
    const combinedCount = data.filter((r) => r.note.includes('합산입금')).length;
    const unmappedCount = data.filter((r) => r.note.includes('미매핑') || r.note.includes('미발행') || r.note.includes('미확인')).length;
    const normalCount = data.filter((r) => !r.note || r.status === 'normal').length;
    const expenseAppliedCount = data.filter((r) => r.expenseApplied).length;

    return {
      totalCount,
      totalCost,
      totalGovSubsidy,
      partialCount,
      combinedCount,
      unmappedCount,
      normalCount,
      expenseAppliedCount,
    };
  }, [data]);

  // 필터링 및 정렬
  const filteredData = useMemo(() => {
    return data
      .filter((row) => {
        // 월 필터
        if (selectedMonth !== 'all' && row.claimMonth !== selectedMonth) {
          return false;
        }

        // 상태 필터
        if (statusFilter === 'need_review') {
          if (!row.note) return false;
        } else if (statusFilter === 'partial') {
          if (!row.note.includes('부분입금')) return false;
        } else if (statusFilter === 'combined') {
          if (!row.note.includes('합산입금')) return false;
        } else if (statusFilter === 'unmapped') {
          if (!row.note.includes('미매핑') && !row.note.includes('미발행') && !row.note.includes('미확인')) return false;
        } else if (statusFilter === 'normal') {
          if (row.note && row.status !== 'normal') return false;
        }

        // 검색어 필터
        if (searchTerm.trim()) {
          const q = searchTerm.toLowerCase();
          const matchCompany = row.companyName.toLowerCase().includes(q);
          const matchCode = row.customerCode.toLowerCase().includes(q);
          const matchCourse = row.courseName.toLowerCase().includes(q);
          const matchNote = row.note.toLowerCase().includes(q);
          return matchCompany || matchCode || matchCourse || matchNote;
        }

        return true;
      })
      .sort((a, b) => {
        const valA = a[sortField];
        const valB = b[sortField];

        // 회차, 인원, 금액 등 숫자형 필드 전용 정밀 정렬
        if (sortField === 'hrdRound' || sortField === 'totalCost' || sortField === 'govSubsidy' || sortField === 'headcount') {
          const numA = typeof valA === 'number' ? valA : parseFloat(String(valA || '').replace(/[^0-9.-]/g, '')) || 0;
          const numB = typeof valB === 'number' ? valB : parseFloat(String(valB || '').replace(/[^0-9.-]/g, '')) || 0;
          if (numA !== numB) {
            return sortAsc ? numA - numB : numB - numA;
          }
        }

        if (typeof valA === 'number' && typeof valB === 'number') {
          return sortAsc ? valA - valB : valB - valA;
        }

        // 자연어 숫자 정렬 (1회차, 2회차, 10회차 등)
        return sortAsc
          ? String(valA || '').localeCompare(String(valB || ''), undefined, { numeric: true, sensitivity: 'base' })
          : String(valB || '').localeCompare(String(valA || ''), undefined, { numeric: true, sensitivity: 'base' });
      });
  }, [data, selectedMonth, statusFilter, searchTerm, sortField, sortAsc]);

  // 정렬 핸들러
  const handleSort = (field: keyof IntegratedDataRow) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  // 정렬 아이콘 렌더러
  const renderSortIcon = (field: keyof IntegratedDataRow) => {
    if (sortField !== field) {
      return <ArrowUpDown className="w-2.5 h-2.5 text-slate-400 opacity-60 group-hover:opacity-100 transition" />;
    }
    return sortAsc ? (
      <ArrowUp className="w-2.5 h-2.5 text-blue-600 font-bold animate-in fade-in duration-100" />
    ) : (
      <ArrowDown className="w-2.5 h-2.5 text-blue-600 font-bold animate-in fade-in duration-100" />
    );
  };

  // 인라인 수정 시작
  const startEdit = (row: IntegratedDataRow) => {
    setEditingId(row.id);
    setEditFormData({ ...row });
  };

  // 인라인 수정 저장
  const saveEdit = () => {
    if (!editingId) return;
    const target = data.find((r) => r.id === editingId);
    if (target) {
      const updated: IntegratedDataRow = {
        ...target,
        ...editFormData,
      };
      onUpdateRow(updated);
    }
    setEditingId(null);
    setEditFormData({});
  };

  // 빠른 토글 (비용신청여부)
  const toggleExpenseApplied = (row: IntegratedDataRow) => {
    onUpdateRow({
      ...row,
      expenseApplied: !row.expenseApplied,
    });
  };

  const toggleReceiptIssued = (row: IntegratedDataRow) => {
    if (!isReceiptEligible(row)) return;
    onUpdateRow({
      ...row,
      receiptIssued: !row.receiptIssued,
    });
  };

  // HRD-Net 비용신청 올리기: 증빙을 rpa 폴더에 내보내고 오른쪽 사이드 패널을 연다
  const claimTargetCount = useMemo(() => data.filter(isCostClaimTarget).length, [data]);

  const startCostClaim = async () => {
    if (!window.rpa) {
      onShowToast?.('설치형 프로그램(Electron)에서만 쓸 수 있습니다.', 'error');
      return;
    }
    const payload = buildCostClaimPayload(data);
    const rounds = new Set(payload.rows.map((r) => `${r.course}__${r.round}`)).size;
    if (payload.rows.length === 0) {
      onShowToast?.('수금이 확인되고 비용신청 전인 회차가 없습니다.', 'info');
      return;
    }
    if (!window.confirm(`${rounds}개 회차(${payload.rows.length}행)를 HRD-Net 비용신청 대상으로 내보내고 사이드 패널을 엽니다.
전자계산서 PDF는 rpa 증빙 폴더에 직접 넣어 주세요.`)) return;
    setClaimBusy(true);
    try {
      const exported = await window.rpa.exportClaims(payload);
      if (!exported.saved) {
        onShowToast?.(exported.reason || '내보내기에 실패했습니다.', 'error');
        return;
      }
      onShowToast?.(`내보냄: ${exported.rows}행 · 수납확인서 ${exported.receipts}건 (${exported.root})`, 'success');
      const launched = await window.rpa.launch();
      if (!launched.ok) {
        onShowToast?.(launched.reason || '사이드 패널을 열지 못했습니다.', 'error');
      } else {
        await window.rpaApi?.call({ method: 'POST', path: '/api/run', body: { args: ['organize'] } });
        setRunModalOpen(true);
      }
    } catch (error) {
      onShowToast?.(`비용신청 연결 실패: ${error instanceof Error ? error.message : String(error)}`, 'error');
    } finally {
      setClaimBusy(false);
    }
  };

  const openRpaPanel = async () => {
    if (!window.rpa) return;
    setClaimBusy(true);
    try {
      const launched = await window.rpa.launch();
      onShowToast?.(launched.ok ? '사이드 패널을 열었습니다.' : launched.reason || '사이드 패널을 열지 못했습니다.', launched.ok ? 'success' : 'error');
    } finally {
      setClaimBusy(false);
    }
  };

  // RPA가 만든 완료처리대상 → 비용신청여부 일괄 체크
  const applyCompletedClaims = async () => {
    if (!window.rpa) return;
    const {items} = await window.rpa.completed();
    const done = new Set(items.map((i) => roundKey(i.course, i.round)));
    let changed = 0;
    data.forEach((row) => {
      if (!row.expenseApplied && done.has(roundKey(row.courseName, row.hrdRound))) {
        onUpdateRow({...row, expenseApplied: true});
        changed += 1;
      }
    });
    onShowToast?.(changed ? `비용신청 완료 ${changed}행을 반영했습니다.` : '새로 반영할 완료 건이 없습니다.', changed ? 'success' : 'info');
  };

  const openReceiptManager = () => {
    setInitialReceiptGroupKey(null);
    setReceiptModalOpen(true);
  };

  const openQuickReceipt = (row: IntegratedDataRow) => {
    setInitialReceiptGroupKey(groupReceiptRows([row])[0]?.key || null);
    setReceiptModalOpen(true);
  };

  const handleReceiptExported = (rowIds: string[]) => {
    const exportedIds = new Set(rowIds);
    data.forEach((row) => {
      if (exportedIds.has(row.id) && !row.receiptIssued) {
        onUpdateRow({...row, receiptIssued: true});
      }
    });
  };

  // 훈련기간 축약 헬퍼 (2026-04-22~2026-05-21 -> 26.04.22~05.21)
  const formatPeriodCompact = (p: string) => {
    if (!p) return '-';
    // ex: 2026-04-22~2026-05-21
    const parts = p.split('~');
    if (parts.length === 2) {
      const start = parts[0].trim().replace(/^20(\d\d)-(\d\d)-(\d\d)$/, '$1.$2.$3');
      const end = parts[1].trim().replace(/^20\d\d-(\d\d)-(\d\d)$/, '$1.$2');
      return `${start}~${end}`;
    }
    return p;
  };

  return (
    <div className="space-y-3.5 w-full">
      {/* Metric Cards Banner (High Density 1-Row Grid) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <div className="bg-white p-2.5 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-500">총 훈련 건수</span>
            <Layers className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <p className="mt-0.5 text-lg font-bold text-slate-900 leading-tight">
            {stats.totalCount.toLocaleString()}<span className="text-[11px] font-normal text-slate-500 ml-1">건</span>
          </p>
          <p className="text-[10px] text-slate-400">비용신청 {stats.expenseAppliedCount}건 완료</p>
        </div>

        <div className="bg-white p-2.5 rounded-xl border border-slate-200 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-500">총 훈련비 청구액</span>
            <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <p className="mt-0.5 text-lg font-bold text-slate-900 leading-tight">
            {stats.totalCost.toLocaleString()}<span className="text-[11px] font-normal text-slate-500 ml-1">원</span>
          </p>
          <p className="text-[10px] text-slate-400">지원금 {stats.totalGovSubsidy.toLocaleString()}원</p>
        </div>

        <div
          onClick={() => setStatusFilter(statusFilter === 'partial' ? 'all' : 'partial')}
          className={`p-2.5 rounded-xl border transition cursor-pointer ${
            statusFilter === 'partial'
              ? 'bg-amber-100/70 border-amber-400 ring-2 ring-amber-400/40'
              : 'bg-amber-50/60 border-amber-200 hover:bg-amber-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-amber-800">부분입금 확인필요</span>
            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          </div>
          <p className="mt-0.5 text-lg font-bold text-amber-950 leading-tight">
            {stats.partialCount}<span className="text-[11px] font-normal text-amber-700 ml-1">건</span>
          </p>
          <p className="text-[10px] text-amber-700">분할입금 / 날짜누적</p>
        </div>

        <div
          onClick={() => setStatusFilter(statusFilter === 'combined' ? 'all' : 'combined')}
          className={`p-2.5 rounded-xl border transition cursor-pointer ${
            statusFilter === 'combined'
              ? 'bg-purple-100/70 border-purple-400 ring-2 ring-purple-400/40'
              : 'bg-purple-50/60 border-purple-200 hover:bg-purple-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-purple-800">합산입금 확인필요</span>
            <span className="w-2 h-2 rounded-full bg-purple-500"></span>
          </div>
          <p className="mt-0.5 text-lg font-bold text-purple-950 leading-tight">
            {stats.combinedCount}<span className="text-[11px] font-normal text-purple-700 ml-1">건</span>
          </p>
          <p className="text-[10px] text-purple-700">동일거래처 다중과정</p>
        </div>

        <div
          onClick={() => setStatusFilter(statusFilter === 'unmapped' ? 'all' : 'unmapped')}
          className={`p-2.5 rounded-xl border transition cursor-pointer ${
            statusFilter === 'unmapped'
              ? 'bg-rose-100/70 border-rose-400 ring-2 ring-rose-400/40'
              : 'bg-rose-50/60 border-rose-200 hover:bg-rose-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-rose-800">미입금/미발행 확인필요</span>
            <span className="w-2 h-2 rounded-full bg-rose-500"></span>
          </div>
          <p className="mt-0.5 text-lg font-bold text-rose-950 leading-tight">
            {stats.unmappedCount}<span className="text-[11px] font-normal text-rose-700 ml-1">건</span>
          </p>
          <p className="text-[10px] text-rose-700">입금 또는 세금계산서 확인</p>
        </div>

        <div
          onClick={() => setStatusFilter(statusFilter === 'normal' ? 'all' : 'normal')}
          className={`p-2.5 rounded-xl border transition cursor-pointer ${
            statusFilter === 'normal'
              ? 'bg-emerald-100/70 border-emerald-400 ring-2 ring-emerald-400/40'
              : 'bg-emerald-50/60 border-emerald-200 hover:bg-emerald-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold text-emerald-800">정상 매핑 완료</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          </div>
          <p className="mt-0.5 text-lg font-bold text-emerald-950 leading-tight">
            {stats.normalCount}<span className="text-[11px] font-normal text-emerald-700 ml-1">건</span>
          </p>
          <p className="text-[10px] text-emerald-700">이상 없음</p>
        </div>
      </div>

      {/* Control Bar (Filters, Search, Buttons) */}
      <div className="bg-white px-3.5 py-2.5 rounded-xl border border-slate-200 shadow-2xs flex flex-wrap items-center justify-between gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {/* Status Filter Dropdown */}
          <div className="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
            <Filter className="w-3 h-3 text-slate-500" />
            <select
              id="filter-status-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as any)}
              className="bg-transparent text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="all">전체 상태 ({data.length})</option>
              <option value="need_review">⚠️ 확인필요 전체 ({stats.partialCount + stats.combinedCount + stats.unmappedCount})</option>
              <option value="partial">부분입금 확인필요 ({stats.partialCount})</option>
              <option value="combined">합산입금 확인필요 ({stats.combinedCount})</option>
              <option value="unmapped">미입금/미발행 확인필요 ({stats.unmappedCount})</option>
              <option value="normal">정상 완료 건 ({stats.normalCount})</option>
            </select>
          </div>

          {/* Month Filter */}
          <div className="flex items-center space-x-1.5 bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
            <Calendar className="w-3 h-3 text-slate-500" />
            <select
              id="filter-month-select"
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="bg-transparent text-[11px] font-medium text-slate-700 focus:outline-none cursor-pointer"
            >
              <option value="all">전체 청구월</option>
              {availableMonths.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>

          {/* Search Box */}
          <div className="relative min-w-[200px] sm:min-w-[240px]">
            <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              id="input-search-data"
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="사업장명, 거래처코드, 과정명..."
              className="w-full pl-7 pr-2.5 py-1 text-[11px] bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-500 focus:bg-white"
            />
          </div>

          {/* Screen Fit Badge */}
          <div className="hidden xl:flex items-center space-x-1 px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200/80 text-[10.5px]">
            <Maximize2 className="w-3 h-3" />
            <span>화면 100% 핏 모드 (좌우 스크롤 없음)</span>
          </div>
        </div>

        {/* Right action buttons */}
        <div className="flex items-center space-x-2">
          {stats.unmappedCount > 0 && (
            <button
              id="btn-goto-mappings-alert"
              onClick={onNavigateToMappings}
              className="flex items-center space-x-1 px-2.5 py-1 text-[11px] font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition"
            >
              <AlertTriangle className="w-3 h-3 text-rose-600" />
              <span>미입금/미발행 ({stats.unmappedCount})</span>
            </button>
          )}

          <button
            id="btn-open-receipt-export"
            type="button"
            onClick={openReceiptManager}
            disabled={receiptGroups.length === 0}
            className="flex items-center space-x-1.5 px-3 py-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="수금일자가 확인된 사업장의 수납확인서를 출력합니다."
          >
            <FileText className="w-3 h-3" />
            <span>수납확인서 ({receiptGroups.length})</span>
          </button>

          {window.rpa && (
            <>
              <button
                id="btn-start-cost-claim"
                type="button"
                onClick={startCostClaim}
                disabled={claimBusy || claimTargetCount === 0}
                className="flex items-center space-x-1.5 px-3 py-1 text-[11px] font-bold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg shadow-2xs transition disabled:opacity-40 disabled:cursor-not-allowed"
                title="수금 확인된 회차를 HRD-Net 비용신청으로 올립니다. 로그인과 최종 신청은 사람이 합니다."
              >
                <span>{claimBusy ? '여는 중...' : `HRD-Net 비용신청 올리기 (${claimTargetCount})`}</span>
              </button>
              <button
                id="btn-open-rpa-run"
                type="button"
                onClick={() => setRunModalOpen(true)}
                className="px-2.5 py-1 text-[11px] font-semibold text-teal-800 bg-teal-50 hover:bg-teal-100 border border-teal-300 rounded-lg transition"
                title="회차를 골라 모의 실행 · 점검 · 미리 채워 보기 · 신청을 실행합니다."
              >
                회차 실행
              </button>
              <button
                id="btn-open-rpa-panel"
                type="button"
                onClick={openRpaPanel}
                disabled={claimBusy}
                className="px-2.5 py-1 text-[11px] font-semibold text-indigo-700 bg-white hover:bg-indigo-50 border border-indigo-300 rounded-lg transition disabled:opacity-40"
                title="증빙을 다시 만들지 않고 사이드 패널(RPA 엔진)만 엽니다."
              >
                사이드 패널 열기
              </button>
              <button
                id="btn-apply-cost-claim-done"
                type="button"
                onClick={applyCompletedClaims}
                className="px-2.5 py-1 text-[11px] font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition"
                title="RPA 결과의 완료처리 대상을 비용신청여부에 반영합니다."
              >
                결과 반영
              </button>
            </>
          )}

          <button
            id="btn-export-excel-main"
            onClick={onExportExcel}
            className="flex items-center space-x-1.5 px-3 py-1 text-[11px] font-semibold text-white bg-blue-600 hover:bg-blue-500 active:bg-blue-700 rounded-lg shadow-2xs transition"
          >
            <Download className="w-3 h-3" />
            <span>최종 DATA 엑셀 저장</span>
          </button>
        </div>
      </div>

      {/* Main DATA Table - 100% Screen Fit, No Horizontal Scroll */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden w-full">
        {/* Table Sub-header */}
        <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-[11px] text-slate-500">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-800">통합 DATA 시트</span>
            <span className="text-slate-300">|</span>
            <span>조회 결과: <strong className="text-slate-900">{filteredData.length}</strong>건</span>
          </div>
          <div className="flex items-center space-x-2.5 text-[10.5px]">
            <span className="inline-flex items-center"><span className="w-2 h-2 rounded-full bg-amber-400 mr-1"></span>부분입금</span>
            <span className="inline-flex items-center"><span className="w-2 h-2 rounded-full bg-purple-400 mr-1"></span>합산입금</span>
            <span className="inline-flex items-center"><span className="w-2 h-2 rounded-full bg-rose-400 mr-1"></span>미입금/미발행</span>
            <span className="text-slate-400 ml-1 hidden sm:inline">💡 더블클릭 또는 수정 버튼으로 편집 가능</span>
          </div>
        </div>

        {/* Dense Table Layout (Full Fit Width) */}
        <div className="w-full overflow-x-hidden max-h-[640px] overflow-y-auto scrollbar-thin">
          <table className="w-full table-fixed text-left border-collapse text-[11px]">
            <thead className="bg-slate-100/90 sticky top-0 z-20 border-b border-slate-200 font-semibold text-slate-700 text-[10.5px] uppercase select-none">
              <tr>
                {/* No (3%) */}
                <th className="py-2 px-1 text-center w-[3%] text-slate-500">No</th>

                {/* 청구월 (4%) */}
                <th
                  onClick={() => handleSort('claimMonth')}
                  className={`py-2 px-1 text-center w-[4%] cursor-pointer hover:bg-slate-200/60 transition ${
                    sortField === 'claimMonth' ? 'bg-slate-200/70 text-blue-700' : ''
                  }`}
                  title="클릭하여 청구월 오름차순/내림차순 정렬"
                >
                  <div className="flex items-center justify-center space-x-0.5 group">
                    <span>월</span>
                    {renderSortIcon('claimMonth')}
                  </div>
                </th>

                {/* 거래처코드 (6%) */}
                <th
                  onClick={() => handleSort('customerCode')}
                  className={`py-2 px-1 text-center w-[6%] cursor-pointer hover:bg-slate-200/60 transition ${
                    sortField === 'customerCode' ? 'bg-slate-200/70 text-blue-700' : ''
                  }`}
                  title="클릭하여 거래처코드 오름차순/내림차순 정렬"
                >
                  <div className="flex items-center justify-center space-x-0.5 group">
                    <span>거래처코드</span>
                    {renderSortIcon('customerCode')}
                  </div>
                </th>

                {/* 훈련실시사업장명 (12%) */}
                <th
                  onClick={() => handleSort('companyName')}
                  className={`py-2 px-1.5 w-[10.5%] cursor-pointer hover:bg-slate-200/60 transition ${
                    sortField === 'companyName' ? 'bg-slate-200/70 text-blue-700' : ''
                  }`}
                  title="클릭하여 사업장명 오름차순/내림차순 정렬"
                >
                  <div className="flex items-center space-x-0.5 group">
                    <span>훈련실시사업장명</span>
                    {renderSortIcon('companyName')}
                  </div>
                </th>

                {/* 과정명 (14%) */}
                <th className="py-2 px-1.5 w-[12%]">과정명</th>

                {/* 훈련기간 (9%) */}
                <th className="py-2 px-1 text-center w-[8.5%]">훈련기간</th>

                {/* HRD회차 (3.5%) */}
                <th
                  onClick={() => handleSort('hrdRound')}
                  className={`py-2 px-0.5 text-center w-[3.5%] cursor-pointer hover:bg-slate-200/60 transition ${
                    sortField === 'hrdRound' ? 'bg-slate-200/70 text-blue-700' : ''
                  }`}
                  title="클릭하여 회차 오름차순/내림차순 정렬"
                >
                  <div className="flex items-center justify-center space-x-0.5 group">
                    <span>회차</span>
                    {renderSortIcon('hrdRound')}
                  </div>
                </th>

                {/* 실시인원 (3.5%) */}
                <th className="py-2 px-0.5 text-center w-[3.5%]">인원</th>

                {/* 훈련비총액 (7%) */}
                <th
                  onClick={() => handleSort('totalCost')}
                  className={`py-2 px-1 text-right w-[7%] cursor-pointer hover:bg-slate-200/60 transition ${
                    sortField === 'totalCost' ? 'bg-slate-200/70 text-blue-700' : ''
                  }`}
                  title="클릭하여 훈련비 오름차순/내림차순 정렬"
                >
                  <div className="flex items-center justify-end space-x-0.5 group">
                    <span>훈련비총액</span>
                    {renderSortIcon('totalCost')}
                  </div>
                </th>

                {/* 정부지원금 (7%) */}
                <th className="py-2 px-1 text-right w-[7%]">정부지원금</th>

                {/* 계산서발행일자 (7%) */}
                <th className="py-2 px-1 text-center w-[7%]">계산서발행</th>

                {/* 수금일자 (6.5%) */}
                <th className="py-2 px-1 text-center w-[6.5%]">수금일자</th>

                {/* 수납확인서 (5%) */}
                <th className="py-2 px-0.5 text-center w-[5%]">수납확인서</th>

                {/* 비용신청 (4%) */}
                <th className="py-2 px-0.5 text-center w-[4%]">비용신청</th>

                {/* 자동입력 상태 (RPA) */}
                {window.rpa && <th className="py-2 px-0.5 text-center w-[5%]" title="HRD-Net 자동입력 진행 상태">자동입력</th>}

                {/* 환급일자 (6%) */}
                <th className="py-2 px-1 text-center w-[6%]">환급일자</th>

                {/* 비고 (신규) (8%) */}
                <th className="py-2 px-1 text-center w-[8%]">비고 (예외감지)</th>

                {/* 관리 (3.5%) */}
                <th className="py-2 px-0.5 text-center w-[3.5%]">관리</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-200/70 text-slate-800">
              {filteredData.length === 0 ? (
                <tr>
                  <td colSpan={18} className="py-16 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center space-y-2">
                      <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400">
                        <Layers className="w-5 h-5" />
                      </div>
                      <p className="text-sm font-semibold text-slate-700">현재 로드된 데이터가 없습니다.</p>
                      <p className="text-xs text-slate-400 max-w-md">
                        <strong>[공용폴더 연결]</strong> 버튼을 통해 사내 공용폴더를 지정하거나, <strong>[공용폴더 원본 관리]</strong> 탭에서 원본 엑셀 파일을 업로드해주세요.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredData.map((row, idx) => {
                  const isEditing = editingId === row.id;

                  // 행 강조 색상 스타일
                  let rowBgClass = 'hover:bg-slate-50/80';
                  let noteBadgeClass = 'bg-slate-100 text-slate-600';

                  if (row.note.includes('부분입금')) {
                    rowBgClass = 'bg-amber-50/40 hover:bg-amber-50/80 border-l-2 border-l-amber-500';
                    noteBadgeClass = 'bg-amber-100 text-amber-900 border border-amber-300 font-semibold';
                  } else if (row.note.includes('합산입금')) {
                    rowBgClass = 'bg-purple-50/40 hover:bg-purple-50/80 border-l-2 border-l-purple-500';
                    noteBadgeClass = 'bg-purple-100 text-purple-900 border border-purple-300 font-semibold';
                  } else if (row.note.includes('미매핑') || row.note.includes('미발행') || row.note.includes('미확인')) {
                    rowBgClass = 'bg-rose-50/40 hover:bg-rose-50/80 border-l-2 border-l-rose-500';
                    noteBadgeClass = 'bg-rose-100 text-rose-900 border border-rose-300 font-semibold';
                  } else if (row.invoiceDate && row.depositDate) {
                    noteBadgeClass = 'bg-emerald-50 text-emerald-700 border border-emerald-200';
                  }

                  return (
                    <tr
                      key={row.id}
                      className={`transition-colors ${rowBgClass}`}
                      onDoubleClick={() => !isEditing && startEdit(row)}
                    >
                      {/* No */}
                      <td className="py-1.5 px-1 text-center text-slate-400 font-mono text-[10px]">
                        {idx + 1}
                      </td>

                      {/* 청구월 */}
                      <td className="py-1.5 px-1 text-center font-medium">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.claimMonth || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, claimMonth: e.target.value })}
                            className="w-full px-1 py-0.5 border rounded bg-white text-[11px] text-center"
                          />
                        ) : (
                          row.claimMonth
                        )}
                      </td>

                      {/* 거래처코드 */}
                      <td className="py-1.5 px-1 text-center font-mono">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.customerCode || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, customerCode: e.target.value })}
                            className="w-full px-1 py-0.5 border rounded bg-white text-[11px] font-mono text-center"
                          />
                        ) : row.customerCode ? (
                          <span className="font-semibold text-slate-800">{row.customerCode}</span>
                        ) : (
                          <span className="text-rose-500 font-medium italic text-[10px]">미등록</span>
                        )}
                      </td>

                      {/* 훈련실시사업장명 */}
                      <td className="py-1.5 px-1.5 font-medium truncate" title={row.companyName}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.companyName || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, companyName: e.target.value })}
                            className="w-full px-1 py-0.5 border rounded bg-white text-[11px]"
                          />
                        ) : (
                          <span className="text-slate-900 font-semibold truncate block">
                            {row.companyName}
                          </span>
                        )}
                      </td>

                      {/* 과정명 */}
                      <td className="py-1.5 px-1.5 text-slate-700 truncate" title={row.courseName}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.courseName || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, courseName: e.target.value })}
                            className="w-full px-1 py-0.5 border rounded bg-white text-[11px]"
                          />
                        ) : (
                          <span className="truncate block">{row.courseName}</span>
                        )}
                      </td>

                      {/* 훈련기간 */}
                      <td
                        className="py-1.5 px-1 text-center font-mono text-[10px] text-slate-600 truncate"
                        title={row.period}
                      >
                        {formatPeriodCompact(row.period)}
                      </td>

                      {/* HRD회차 */}
                      <td className="py-1.5 px-0.5 text-center font-mono text-slate-600 text-[10.5px]">
                        {row.hrdRound}
                      </td>

                      {/* 실시인원 */}
                      <td className="py-1.5 px-0.5 text-center font-semibold text-slate-700 text-[10.5px]">
                        {row.headcount}
                      </td>

                      {/* 훈련비총액 */}
                      <td className="py-1.5 px-1 text-right font-mono font-medium text-slate-900 truncate">
                        {row.totalCost.toLocaleString()}
                      </td>

                      {/* 정부지원금 */}
                      <td className="py-1.5 px-1 text-right font-mono text-slate-600 truncate">
                        {row.govSubsidy.toLocaleString()}
                      </td>

                      {/* 계산서발행일자 */}
                      <td className="py-1.5 px-1 text-center font-mono text-[10.5px]">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.invoiceDate || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, invoiceDate: e.target.value })}
                            placeholder="YYYY-MM-DD"
                            className="w-full px-0.5 py-0.5 border rounded bg-white text-[10px] font-mono text-center"
                          />
                        ) : row.invoiceDate ? (
                          <span className="text-slate-800">{row.invoiceDate}</span>
                        ) : (
                          <span className="text-slate-400 italic text-[10px]">미발행</span>
                        )}
                      </td>

                      {/* 수금일자 */}
                      <td className="py-1.5 px-1 text-center font-mono text-[10.5px] truncate" title={row.depositDate}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.depositDate || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, depositDate: e.target.value })}
                            placeholder="예: 2026-08-18"
                            className="w-full px-0.5 py-0.5 border rounded bg-white text-[10px] font-mono text-center"
                          />
                        ) : row.depositDate ? (
                          <span className={row.note.includes('부분입금') ? 'font-bold text-amber-900' : 'text-slate-800'}>
                            {row.depositDate}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic text-[10px]">미입금</span>
                        )}
                      </td>

                      {/* 수납확인서 출력 여부 및 빠른 미리보기 */}
                      <td className="py-1.5 px-0.5 text-center">
                        {isReceiptEligible(row) ? (
                          <div className="inline-flex items-center justify-center gap-0.5">
                            <button
                              type="button"
                              onClick={() => toggleReceiptIssued(row)}
                              className="p-0.5 rounded hover:bg-emerald-50 transition"
                              title="수납확인서 출력 여부를 직접 변경"
                            >
                              {row.receiptIssued ? (
                                <CheckSquare className="w-3.5 h-3.5 text-emerald-600" />
                              ) : (
                                <Square className="w-3.5 h-3.5 text-slate-400" />
                              )}
                            </button>
                            <button
                              type="button"
                              onClick={() => openQuickReceipt(row)}
                              className="p-1 rounded text-emerald-600 hover:text-emerald-800 hover:bg-emerald-50 transition"
                              title="수납확인서 미리보기"
                            >
                              <FileText className="w-3 h-3" />
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-300">-</span>
                        )}
                      </td>

                      {/* 비용신청여부 */}
                      <td className="py-1.5 px-0.5 text-center">
                        <button
                          type="button"
                          onClick={() => toggleExpenseApplied(row)}
                          className="inline-flex items-center justify-center p-0.5 rounded hover:bg-slate-200 transition"
                          title="클릭하여 신청여부 토글"
                        >
                          {row.expenseApplied ? (
                            <CheckSquare className="w-3.5 h-3.5 text-blue-600" />
                          ) : (
                            <Square className="w-3.5 h-3.5 text-slate-400" />
                          )}
                        </button>
                      </td>

                      {/* 자동입력 상태 (RPA) */}
                      {window.rpa && (
                        <td className="py-1.5 px-0.5 text-center">{rpaBadge(rpaStatus[roundKey(row.courseName, row.hrdRound)])}</td>
                      )}

                      {/* 환급일자 */}
                      <td className="py-1.5 px-1 text-center font-mono text-[10px] text-slate-600">
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.refundDate || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, refundDate: e.target.value })}
                            placeholder="YYYY-MM-DD"
                            className="w-full px-0.5 py-0.5 border rounded bg-white text-[10px] text-center"
                          />
                        ) : (
                          row.refundDate || '-'
                        )}
                      </td>

                      {/* 비고 (신규) */}
                      <td className="py-1.5 px-1 text-center truncate" title={row.note}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editFormData.note || ''}
                            onChange={(e) => setEditFormData({ ...editFormData, note: e.target.value })}
                            className="w-full px-1 py-0.5 border rounded bg-white text-[10.5px]"
                          />
                        ) : row.note ? (
                          <span className={`px-1.5 py-0.5 rounded text-[10px] truncate block ${noteBadgeClass}`}>
                            {row.note}
                          </span>
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>

                      {/* 관리 버튼 */}
                      <td className="py-1.5 px-0.5 text-center">
                        {isEditing ? (
                          <button
                            type="button"
                            onClick={saveEdit}
                            className="p-1 rounded bg-blue-600 hover:bg-blue-700 text-white shadow-2xs transition"
                            title="저장"
                          >
                            <Save className="w-3 h-3" />
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => startEdit(row)}
                            className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                            title="직접 수정"
                          >
                            <Edit2 className="w-3 h-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <RpaRunModal isOpen={runModalOpen} onClose={() => setRunModalOpen(false)} onShowToast={onShowToast} />

      <ReceiptExportModal
        isOpen={receiptModalOpen}
        data={data}
        initialGroupKey={initialReceiptGroupKey}
        onClose={() => setReceiptModalOpen(false)}
        onShowToast={onShowToast}
        onExported={handleReceiptExported}
      />
    </div>
  );
};
