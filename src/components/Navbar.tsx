import React from 'react';
import { Table, UploadCloud, BookOpen, Download, RefreshCw, FolderSync, FolderOpen, CreditCard, FileText, Building2, Pencil, Plus } from 'lucide-react';
import { TrainingCenter } from '../types';

interface NavbarProps {
  activeTab: 'data' | 'deposit-invoice' | 'upload' | 'mappings' | 'claim';
  setActiveTab: (tab: 'data' | 'deposit-invoice' | 'upload' | 'mappings' | 'claim') => void;
  totalCount: number;
  needReviewCount: number;
  depositCount?: number;
  onExportExcel: () => void;
  onRefreshSharedFolder: () => Promise<void>;
  onConnectDirectory?: () => void;
  onOpenManual?: () => void;
  isRefreshing: boolean;
  lastSyncTime: string | null;
  centers: TrainingCenter[];
  activeCenterId: string;
  onChangeCenter: (centerId: string) => void;
  onEditCenter: () => void;
  onAddCenter: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  totalCount,
  needReviewCount,
  depositCount = 0,
  onExportExcel,
  onRefreshSharedFolder,
  onConnectDirectory,
  onOpenManual,
  isRefreshing,
  lastSyncTime,
  centers,
  activeCenterId,
  onChangeCenter,
  onEditCenter,
  onAddCenter,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-40">
      <div className="w-full px-3 sm:px-5 lg:px-6">
        <div className="flex min-h-15 flex-wrap items-center justify-between gap-2 py-2">
          {/* Logo & Title */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-blue-600 flex items-center justify-center font-bold text-white text-lg shadow-md shadow-blue-500/20">
              <Table className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-slate-100 tracking-tight">수주 및 비용 통합 관리</span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 font-medium border border-blue-500/30">
                  DATA 자동 매핑 v2.2.0
                </span>
              </div>
              <p className="text-xs text-slate-400">훈련내역 · 계산서 · 입금내역 자동 매칭 & 예외 감지</p>
            </div>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800/80 p-1.5">
            {centers.length > 1 && (
              <>
            <div className="flex items-center gap-2 px-2">
              <Building2 className="h-4 w-4 text-blue-400" />
              <div className="leading-tight">
                <p className="text-[10px] font-medium text-slate-400">현재 작업공간</p>
                <select
                  value={activeCenterId}
                  onChange={(event) => onChangeCenter(event.target.value)}
                  className="max-w-36 cursor-pointer bg-transparent text-xs font-bold text-white outline-none"
                  aria-label="연수원 작업공간 선택"
                >
                  {centers.map((center) => (
                    <option key={center.id} value={center.id} className="bg-slate-800 text-white">
                      {center.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button
              type="button"
              onClick={onEditCenter}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-slate-700 hover:text-white"
              title="현재 연수원명 편집"
              aria-label="현재 연수원명 편집"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
              </>
            )}
            <button
              type="button"
              onClick={onAddCenter}
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-600 bg-slate-700 text-slate-200 transition hover:border-blue-500 hover:bg-blue-600 hover:text-white"
              title="새 연수원 추가"
              aria-label="새 연수원 추가"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center space-x-1 bg-slate-800/80 p-1 rounded-xl border border-slate-700/60">
            <button
              id="nav-tab-data"
              onClick={() => setActiveTab('data')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'data'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <Table className="w-4 h-4" />
              <span>통합 DATA 시트</span>
              {needReviewCount > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-amber-500 text-slate-950 font-bold">
                  {needReviewCount}
                </span>
              )}
            </button>

            <button
              id="nav-tab-deposit-invoice"
              onClick={() => setActiveTab('deposit-invoice')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'deposit-invoice'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <CreditCard className="w-4 h-4" />
              <span>입금-계산서 대조</span>
              {depositCount > 0 && (
                <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-500/30 text-emerald-300 font-bold">
                  {depositCount}
                </span>
              )}
            </button>

            {window.rpa && (
              <button
                id="nav-tab-claim"
                onClick={() => setActiveTab('claim')}
                className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                  activeTab === 'claim'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-indigo-200 hover:text-white hover:bg-slate-700/50'
                }`}
              >
                <FileText className="w-4 h-4" />
                <span>HRD-Net 비용신청</span>
              </button>
            )}

            <button
              id="nav-tab-upload"
              onClick={() => setActiveTab('upload')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'upload'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <FolderSync className="w-4 h-4" />
              <span>공용폴더 원본 관리</span>
            </button>

            <button
              id="nav-tab-mappings"
              onClick={() => setActiveTab('mappings')}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === 'mappings'
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700/50'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span>매핑 사전 관리</span>
            </button>
          </nav>

          {/* Quick Actions */}
          <div className="flex items-center space-x-2">
            {onConnectDirectory && (
              <button
                id="btn-connect-shared-navbar"
                onClick={onConnectDirectory}
                className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-700 transition cursor-pointer"
                title="사내 공용폴더 또는 네트워크 드라이브를 지정/연결합니다."
              >
                <FolderOpen className="w-3.5 h-3.5 text-blue-400" />
                <span>공용폴더 연결</span>
              </button>
            )}

            <button
              id="btn-refresh-shared-navbar"
              onClick={onRefreshSharedFolder}
              disabled={isRefreshing}
              className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-bold text-emerald-300 hover:text-white bg-emerald-950/60 hover:bg-emerald-900/80 rounded-lg border border-emerald-800/80 transition disabled:opacity-50 cursor-pointer"
              title="공용폴더의 원본 엑셀 파일을 다시 읽어와 최신 데이터로 새로고침합니다."
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
              <span>{isRefreshing ? '동기화 중...' : '공용폴더 새로고침'}</span>
            </button>

            <button
              id="btn-export-excel-header"
              onClick={onExportExcel}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-500 active:bg-blue-700 rounded-lg shadow-sm transition cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>엑셀 다운로드</span>
            </button>

            {onOpenManual && (
              <button
                id="btn-open-manual-navbar"
                onClick={onOpenManual}
                className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-amber-200 hover:text-white bg-amber-950/60 hover:bg-amber-900/80 rounded-lg border border-amber-800/80 transition shadow-2xs cursor-pointer"
                title="시스템 이용가이드를 열고 PDF로 인쇄/저장합니다."
              >
                <FileText className="w-3.5 h-3.5 text-amber-400" />
                <span>이용가이드(PDF)</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
