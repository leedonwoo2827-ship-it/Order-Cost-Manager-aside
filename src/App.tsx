import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  INITIAL_TRAINING_RECORDS,
  INITIAL_COMPANY_MAPPINGS,
  INITIAL_DEPOSITOR_MAPPINGS,
  INITIAL_INVOICE_RECORDS,
  INITIAL_DEPOSIT_RECORDS,
} from './data/sampleData';
import {
  TrainingRecord,
  CompanyMapping,
  DepositorMapping,
  InvoiceRecord,
  DepositRecord,
  IntegratedDataRow,
  SharedFolderInfo,
  TrainingCenter,
} from './types';
import {
  processMapping,
  exportToExcel,
  scanAndParseFolderFiles,
  readFilesFromDirectoryHandle,
  autoDiscoverCompanyMappings,
  mergeCompanyMappings,
  autoDiscoverDepositorMappings,
  mergeDepositorMappings,
  getTrainingRecordKey,
  mergeTrainingRecords,
  mergeInvoiceRecords,
  mergeDepositRecords,
} from './utils/mappingEngine';
import { Navbar } from './components/Navbar';
import { DataSheetView } from './components/DataSheetView';
import { DepositInvoiceView } from './components/DepositInvoiceView';
import { UploadManager } from './components/UploadManager';
import { MappingDictionaryView } from './components/MappingDictionaryView';
import { ConnectSharedFolderModal } from './components/ConnectSharedFolderModal';
import { ClearDataModal, ClearDataTargets } from './components/ClearDataModal';
import { TeamManualModal } from './components/TeamManualModal';
import { RpaClaimView } from './components/RpaClaimView';
import { AddTrainingCenterModal } from './components/AddTrainingCenterModal';
import { CheckCircle2, AlertCircle, X, FolderSync } from 'lucide-react';

const PRIMARY_CENTER_ID = 'main-center';
const HRD_ARCHIVE_CENTER_ID = 'hrd-archive-center';
const CENTER_LIST_KEY = 'hrd_sync_training_centers_v4';
const ACTIVE_CENTER_KEY = 'hrd_sync_active_training_center_v4';

const DEFAULT_CENTERS: TrainingCenter[] = [
  {
    id: PRIMARY_CENTER_ID,
    name: 'AI 융합',
    color: '#2563eb',
    createdAt: new Date(0).toISOString(),
  },
  {
    id: HRD_ARCHIVE_CENTER_ID,
    name: 'HRD 아카이브',
    color: '#0f766e',
    createdAt: new Date(0).toISOString(),
  },
];

const LEGACY_STORAGE_KEYS = {
  TRAININGS: 'hrd_sync_trainings_v3',
  COMPANY_MAPPINGS: 'hrd_sync_company_mappings_v3',
  DEPOSITOR_MAPPINGS: 'hrd_sync_depositor_mappings_v3',
  INVOICES: 'hrd_sync_invoices_v3',
  DEPOSITS: 'hrd_sync_deposits_v3',
  USER_EDITED_ROWS: 'hrd_sync_user_edited_rows_v3',
  EXPENSE_MAP: 'hrd_sync_expense_map_v3',
  SHARED_FOLDER: 'hrd_sync_shared_folder_v3',
};

function getStorageKeys(centerId: string) {
  if (centerId === PRIMARY_CENTER_ID) return LEGACY_STORAGE_KEYS;

  const suffix = `_v4_${centerId}`;
  return {
    TRAININGS: `hrd_sync_trainings${suffix}`,
    COMPANY_MAPPINGS: `hrd_sync_company_mappings${suffix}`,
    DEPOSITOR_MAPPINGS: `hrd_sync_depositor_mappings${suffix}`,
    INVOICES: `hrd_sync_invoices${suffix}`,
    DEPOSITS: `hrd_sync_deposits${suffix}`,
    USER_EDITED_ROWS: `hrd_sync_user_edited_rows${suffix}`,
    EXPENSE_MAP: `hrd_sync_expense_map${suffix}`,
    SHARED_FOLDER: `hrd_sync_shared_folder${suffix}`,
  };
}

function loadStorage<T>(key: string, fallback: T): T {
  try {
    const saved = localStorage.getItem(key);
    if (!saved) return fallback;
    return JSON.parse(saved);
  } catch (e) {
    console.error(`Failed to load ${key} from localStorage:`, e);
    return fallback;
  }
}

function saveStorage<T>(key: string, data: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(data));
  } catch (e) {
    console.error(`Failed to save ${key} to localStorage:`, e);
  }
}

function loadInitialCenters(): TrainingCenter[] {
  const saved = loadStorage<TrainingCenter[]>(CENTER_LIST_KEY, []);
  if (!Array.isArray(saved) || saved.length === 0) return DEFAULT_CENTERS;

  const centers = saved.map((center) => (
    center.id === PRIMARY_CENTER_ID && center.name === '기본 연수원'
      ? { ...center, name: 'AI 융합' }
      : center
  ));

  for (const defaultCenter of DEFAULT_CENTERS) {
    const alreadyExists = centers.some((center) => (
      center.id === defaultCenter.id
      || center.name.toLocaleLowerCase() === defaultCenter.name.toLocaleLowerCase()
    ));
    if (!alreadyExists) centers.push(defaultCenter);
  }

  return centers;
}

export default function App() {
  const [centerModalMode, setCenterModalMode] = useState<'add' | 'edit' | null>(null);
  const [centers, setCenters] = useState<TrainingCenter[]>(loadInitialCenters);
  const [activeCenterId, setActiveCenterId] = useState(() => {
    const saved = loadStorage<string>(ACTIVE_CENTER_KEY, PRIMARY_CENTER_ID);
    return centers.some((center) => center.id === saved) ? saved : centers[0].id;
  });

  useEffect(() => {
    saveStorage(CENTER_LIST_KEY, centers);
  }, [centers]);

  useEffect(() => {
    saveStorage(ACTIVE_CENTER_KEY, activeCenterId);
  }, [activeCenterId]);

  const handleAddCenter = useCallback((name: string) => {
    const id = `center-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const palette = ['#0f766e', '#7c3aed', '#c2410c', '#be123c', '#0369a1'];
    const nextCenter: TrainingCenter = {
      id,
      name,
      color: palette[centers.length % palette.length],
      createdAt: new Date().toISOString(),
    };
    setCenters((previous) => [...previous, nextCenter]);
    setActiveCenterId(id);
  }, [centers.length]);

  const handleRenameCenter = useCallback((centerId: string, name: string) => {
    setCenters((previous) => previous.map((center) => (
      center.id === centerId ? { ...center, name } : center
    )));
  }, []);

  const activeCenter = centers.find((center) => center.id === activeCenterId) ?? centers[0];

  return (
    <>
      <WorkspaceApp
        key={activeCenter.id}
        center={activeCenter}
        centers={centers}
        onChangeCenter={setActiveCenterId}
        onEditCenter={() => setCenterModalMode('edit')}
        onAddCenter={() => setCenterModalMode('add')}
      />
      <AddTrainingCenterModal
        isOpen={centerModalMode !== null}
        centers={centers}
        editingCenter={centerModalMode === 'edit' ? activeCenter : null}
        onClose={() => setCenterModalMode(null)}
        onAdd={handleAddCenter}
        onRename={handleRenameCenter}
      />
    </>
  );
}

interface WorkspaceAppProps {
  key?: React.Key;
  center: TrainingCenter;
  centers: TrainingCenter[];
  onChangeCenter: (centerId: string) => void;
  onEditCenter: () => void;
  onAddCenter: () => void;
}

function WorkspaceApp({ center, centers, onChangeCenter, onEditCenter, onAddCenter }: WorkspaceAppProps) {
  const STORAGE_KEYS = getStorageKeys(center.id);
  const isPrimaryCenter = center.id === PRIMARY_CENTER_ID;
  const [activeTab, setActiveTab] = useState<'data' | 'deposit-invoice' | 'upload' | 'mappings' | 'claim'>('data');
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isClearModalOpen, setIsClearModalOpen] = useState(false);
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);

  // 영구 저장된 비용신청 체크박스 상태 맵 (Record<key, boolean>)
  const [expenseMap, setExpenseMap] = useState<Record<string, boolean>>(() =>
    loadStorage<Record<string, boolean>>(STORAGE_KEYS.EXPENSE_MAP, {})
  );

  // 핵심 5개 원본 데이터 상태 (로컬스토리지에서 자동 복원)
  const [trainings, setTrainings] = useState<TrainingRecord[]>(() =>
    loadStorage<TrainingRecord[]>(STORAGE_KEYS.TRAININGS, isPrimaryCenter ? INITIAL_TRAINING_RECORDS : [])
  );
  const [companyMappings, setCompanyMappings] = useState<CompanyMapping[]>(() =>
    loadStorage<CompanyMapping[]>(STORAGE_KEYS.COMPANY_MAPPINGS, isPrimaryCenter ? INITIAL_COMPANY_MAPPINGS : [])
  );
  const [depositorMappings, setDepositorMappings] = useState<DepositorMapping[]>(() =>
    loadStorage<DepositorMapping[]>(STORAGE_KEYS.DEPOSITOR_MAPPINGS, isPrimaryCenter ? INITIAL_DEPOSITOR_MAPPINGS : [])
  );
  const [invoices, setInvoices] = useState<InvoiceRecord[]>(() =>
    loadStorage<InvoiceRecord[]>(STORAGE_KEYS.INVOICES, isPrimaryCenter ? INITIAL_INVOICE_RECORDS : [])
  );
  const [deposits, setDeposits] = useState<DepositRecord[]>(() =>
    loadStorage<DepositRecord[]>(STORAGE_KEYS.DEPOSITS, isPrimaryCenter ? INITIAL_DEPOSIT_RECORDS : [])
  );

  // 수동 수정 오버라이드 맵 (사용자가 DATA 시트에서 직접 수정한 행 저장)
  const [userEditedRows, setUserEditedRows] = useState<Map<string, IntegratedDataRow>>(() => {
    const saved = loadStorage<Record<string, IntegratedDataRow>>(STORAGE_KEYS.USER_EDITED_ROWS, {});
    return new Map(Object.entries(saved));
  });

  // 공용 폴더 연동 상태
  const [sharedFolderInfo, setSharedFolderInfo] = useState<SharedFolderInfo>(() =>
    loadStorage<SharedFolderInfo>(STORAGE_KEYS.SHARED_FOLDER, {
      path: 'C:\\사내공용문서\\수주관리',
      name: '수주관리',
      lastSyncTime: '연동 대기 중',
      detectedFiles: {},
      totalFilesFound: 0,
    })
  );

  const [directoryHandle, setDirectoryHandle] = useState<any>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [notification, setNotification] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);

  // 구버전 및 이전 캐시 정리
  useEffect(() => {
    ['hrd_sync_trainings_v2', 'hrd_sync_invoices_v2', 'hrd_sync_deposits_v2', 'hrd_sync_user_edited_rows_v2', 'hrd_sync_expense_map_v2'].forEach(
      (k) => localStorage.removeItem(k)
    );
  }, []);

  // 데이터 변경 시 로컬 스토리지에 자동 저장 (새로고침/재방문 시 유지)
  useEffect(() => {
    saveStorage(STORAGE_KEYS.TRAININGS, trainings);
  }, [trainings]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.COMPANY_MAPPINGS, companyMappings);
  }, [companyMappings]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.DEPOSITOR_MAPPINGS, depositorMappings);
  }, [depositorMappings]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.INVOICES, invoices);
  }, [invoices]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.DEPOSITS, deposits);
  }, [deposits]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.EXPENSE_MAP, expenseMap);
  }, [expenseMap]);

  useEffect(() => {
    const obj: Record<string, IntegratedDataRow> = {};
    userEditedRows.forEach((val, key) => {
      obj[key] = val;
    });
    saveStorage(STORAGE_KEYS.USER_EDITED_ROWS, obj);
  }, [userEditedRows]);

  useEffect(() => {
    saveStorage(STORAGE_KEYS.SHARED_FOLDER, sharedFolderInfo);
  }, [sharedFolderInfo]);

  // 알림 자동 닫힘 타이머
  const showToast = (message: string, type: 'success' | 'info' | 'error' = 'success') => {
    setNotification({ message, type });
    setTimeout(() => {
      setNotification((prev) => (prev?.message === message ? null : prev));
    }, 4500);
  };

  // 자동 매핑 엔진 실행 결과 + 사용자 수정 사항 병합 + 비용신청 체크박스 유지
  const integratedData = useMemo(() => {
    const autoMapped = processMapping(
      trainings,
      companyMappings,
      depositorMappings,
      invoices,
      deposits
    );

    return autoMapped.map((row) => {
      let finalRow = row;
      if (userEditedRows.has(row.id)) {
        finalRow = { ...row, ...userEditedRows.get(row.id)! };
      }

      // 비용신청 체크박스 영구 저장 상태 반영
      const recordKey = getTrainingRecordKey(row);
      if (expenseMap[recordKey] !== undefined) {
        finalRow = { ...finalRow, expenseApplied: expenseMap[recordKey] };
      } else if (expenseMap[row.id] !== undefined) {
        finalRow = { ...finalRow, expenseApplied: expenseMap[row.id] };
      }

      return finalRow;
    });
  }, [trainings, companyMappings, depositorMappings, invoices, deposits, userEditedRows, expenseMap]);

  // 확인필요 건수 계산
  const needReviewCount = useMemo(() => {
    return integratedData.filter(
      (r) =>
        r.note.includes('부분입금') ||
        r.note.includes('합산입금') ||
        r.note.includes('미매핑') ||
        r.note.includes('미발행') ||
        r.note.includes('미확인')
    ).length;
  }, [integratedData]);

  // 행 직접 수정 핸들러 (비용신청 체크박스 상태 즉시 영구 보존)
  const handleUpdateRow = useCallback((updatedRow: IntegratedDataRow) => {
    const recordKey = getTrainingRecordKey(updatedRow);

    // 1. 수동 수정 맵 업데이트
    setUserEditedRows((prev) => {
      const next = new Map(prev);
      next.set(updatedRow.id, updatedRow);
      return next;
    });

    // 2. 비용신청 체크 상태 영구 맵 업데이트
    setExpenseMap((prev) => {
      const next = { ...prev };
      if (recordKey) next[recordKey] = updatedRow.expenseApplied;
      if (updatedRow.id) next[updatedRow.id] = updatedRow.expenseApplied;
      return next;
    });

    // 3. 원본 trainings 리스트에서도 동기화
    setTrainings((prev) =>
      prev.map((tr) => {
        if (tr.id === updatedRow.id || (recordKey && getTrainingRecordKey(tr) === recordKey)) {
          return {
            ...tr,
            expenseApplied: updatedRow.expenseApplied,
            refundDate: updatedRow.refundDate,
          };
        }
        return tr;
      })
    );
  }, []);

  // 엑셀 업로드/새로고침 데이터 증분 병합 (기존 내용 유지 + 신규 내용만 아래에 덧붙임 + 체크상태 보존)
  const handleDataLoaded = useCallback(
    (data: {
      trainings?: TrainingRecord[];
      companyMappings?: CompanyMapping[];
      depositorMappings?: DepositorMapping[];
      invoices?: InvoiceRecord[];
      deposits?: DepositRecord[];
    }) => {
      let targetTrainings = trainings;
      let targetInvoices = invoices;
      let targetCompanyMappings = companyMappings;
      let targetDeposits = deposits;
      let targetDepositorMappings = depositorMappings;

      let addedTrCount = 0;
      if (data.trainings && data.trainings.length > 0) {
        const { mergedList, addedCount } = mergeTrainingRecords(trainings, data.trainings, expenseMap);
        targetTrainings = mergedList;
        addedTrCount = addedCount;
        setTrainings(mergedList);
      }

      let addedInvCount = 0;
      if (data.invoices && data.invoices.length > 0) {
        const { mergedList, addedCount } = mergeInvoiceRecords(invoices, data.invoices);
        targetInvoices = mergedList;
        addedInvCount = addedCount;
        setInvoices(mergedList);
      }

      let addedDepCount = 0;
      if (data.deposits && data.deposits.length > 0) {
        const { mergedList, addedCount } = mergeDepositRecords(deposits, data.deposits);
        targetDeposits = mergedList;
        addedDepCount = addedCount;
        setDeposits(mergedList);
      }

      if (data.companyMappings && data.companyMappings.length > 0) {
        const { mergedList } = mergeCompanyMappings(companyMappings, data.companyMappings);
        targetCompanyMappings = mergedList;
        setCompanyMappings(mergedList);
      }

      if (data.depositorMappings && data.depositorMappings.length > 0) {
        const { mergedList } = mergeDepositorMappings(depositorMappings, data.depositorMappings);
        targetDepositorMappings = mergedList;
        setDepositorMappings(mergedList);
      }

      // 1. 훈련내역과 계산서발행내역을 실시간 대조하여 사전에 없는 신규 거래처 자동 발굴 & 병합
      const companyDiscovery = autoDiscoverCompanyMappings(
        targetTrainings,
        targetInvoices,
        targetCompanyMappings
      );

      let effectiveCompanyMappings = targetCompanyMappings;
      let addedCompanyCount = 0;
      if (companyDiscovery.newMappings.length > 0) {
        const { mergedList, addedCount } = mergeCompanyMappings(
          targetCompanyMappings,
          companyDiscovery.newMappings
        );
        effectiveCompanyMappings = mergedList;
        addedCompanyCount = addedCount;
        setCompanyMappings(mergedList);
      }

      // 2. 입금내역과 최신 거래처매핑 내역을 대조하여 사전에 없는 신규 입금자 매핑 자동 발굴 & 병합
      const depositorDiscovery = autoDiscoverDepositorMappings(
        targetDeposits,
        effectiveCompanyMappings,
        targetDepositorMappings
      );

      let addedDepositorCount = 0;
      if (depositorDiscovery.newMappings.length > 0) {
        const { mergedList, addedCount } = mergeDepositorMappings(
          targetDepositorMappings,
          depositorDiscovery.newMappings
        );
        addedDepositorCount = addedCount;
        setDepositorMappings(mergedList);
      }

      const addedMessages: string[] = [];
      if (addedTrCount > 0) addedMessages.push(`훈련내역 +${addedTrCount}행`);
      if (addedInvCount > 0) addedMessages.push(`계산서 +${addedInvCount}건`);
      if (addedDepCount > 0) addedMessages.push(`입금내역 +${addedDepCount}건`);
      if (addedCompanyCount > 0) addedMessages.push(`신규 거래처 +${addedCompanyCount}건`);
      if (addedDepositorCount > 0) addedMessages.push(`신규 입금자 +${addedDepositorCount}건`);

      if (addedMessages.length > 0) {
        showToast(
          `기존 데이터를 유지하고 ${addedMessages.join(', ')}을(를) 하단에 추가하여 안전하게 저장했습니다!`,
          'success'
        );
      } else {
        showToast('최신 원본과 동기화 완료되었습니다. (기존 데이터 및 체크 상태 유지됨)', 'info');
      }

      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
      setSharedFolderInfo((prev) => ({
        ...prev,
        lastSyncTime: `오늘 ${timeStr}`,
      }));
    },
    [trainings, invoices, deposits, companyMappings, depositorMappings, expenseMap]
  );

  // 공용 폴더 연결 핸들러 (모달 열기 및 폴더 선택)
  const handleConnectDirectory = useCallback(async () => {
    setIsConnectModalOpen(true);
  }, []);

  const handleModalSyncComplete = useCallback((updatedInfo: Partial<SharedFolderInfo>, msg: string) => {
    setSharedFolderInfo((prev) => ({
      ...prev,
      ...updatedInfo,
    }));
    showToast(msg, 'success');
  }, []);

  // 공용 폴더 원본 새로고침 핸들러
  const handleRefreshSharedFolder = useCallback(async () => {
    setIsRefreshing(true);
    try {
      if (directoryHandle) {
        const files = await readFilesFromDirectoryHandle(directoryHandle);
        const scanned = await scanAndParseFolderFiles(files);
        handleDataLoaded(scanned.data);
        const now = new Date();
        const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
        setSharedFolderInfo((prev) => ({
          ...prev,
          lastSyncTime: `오늘 ${timeStr}`,
          detectedFiles: scanned.detectedFiles,
          totalFilesFound: files.length,
        }));
        showToast(`🔄 공용폴더 최신 원본 엑셀 파일을 다시 읽어와 DATA 시트에 실시간 반영했습니다! (${files.length}개 파일)`);
      } else {
        // Mock refresh with timestamp update & rule rerun & auto discovery check
        await new Promise((r) => setTimeout(r, 600));

        const companyDiscovery = autoDiscoverCompanyMappings(trainings, invoices, companyMappings);
        let effectiveCompanyMappings = companyMappings;
        let addedCompanyCount = 0;
        if (companyDiscovery.newMappings.length > 0) {
          const { mergedList, addedCount } = mergeCompanyMappings(
            companyMappings,
            companyDiscovery.newMappings
          );
          effectiveCompanyMappings = mergedList;
          addedCompanyCount = addedCount;
          setCompanyMappings(mergedList);
        }

        const depositorDiscovery = autoDiscoverDepositorMappings(
          deposits,
          effectiveCompanyMappings,
          depositorMappings
        );
        let addedDepositorCount = 0;
        if (depositorDiscovery.newMappings.length > 0) {
          const { mergedList, addedCount } = mergeDepositorMappings(
            depositorMappings,
            depositorDiscovery.newMappings
          );
          addedDepositorCount = addedCount;
          setDepositorMappings(mergedList);
        }

        const now = new Date();
        const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
        setSharedFolderInfo((prev) => ({
          ...prev,
          lastSyncTime: `오늘 ${timeStr}`,
        }));

        if (addedCompanyCount > 0 || addedDepositorCount > 0) {
          const messages = [];
          if (addedCompanyCount > 0) messages.push(`신규 거래처 ${addedCompanyCount}건`);
          if (addedDepositorCount > 0) messages.push(`신규 입금자 ${addedDepositorCount}건`);
          showToast(
            `🔄 공용폴더 동기화 완료: ${messages.join(', ')}이(가) 매핑 사전에 자동 등록되었습니다!`,
            'success'
          );
        } else {
          showToast(`🔄 공용폴더 원본 3종(훈련내역, 계산서, 입금내역) 최신 데이터를 다시 스캔하여 반영 완료! (${timeStr})`);
        }
      }
    } catch (err: any) {
      showToast(`새로고침 중 오류: ${err.message}`, 'error');
    } finally {
      setIsRefreshing(false);
    }
  }, [directoryHandle, handleDataLoaded, trainings, invoices, deposits, companyMappings, depositorMappings]);

  // 공용 폴더 경로 수동 수정
  const handleUpdateSharedPath = useCallback((newPath: string) => {
    setSharedFolderInfo((prev) => ({
      ...prev,
      path: newPath,
    }));
    showToast(`공용폴더 경로가 '${newPath}'(으)로 설정되었습니다.`);
  }, []);

  // 엑셀 다운로드
  const handleExportExcel = useCallback(() => {
    exportToExcel(integratedData, companyMappings, depositorMappings, invoices, deposits, center.name);
    showToast('통합 DATA 엑셀 파일이 성공적으로 다운로드되었습니다.');
  }, [integratedData, companyMappings, depositorMappings, invoices, deposits, center.name]);

  // 거래처 사전 단건 추가
  const handleAddCompanyMapping = useCallback((newMapping: CompanyMapping) => {
    setCompanyMappings((prev) => {
      const { mergedList } = mergeCompanyMappings(prev, [newMapping]);
      return mergedList;
    });
    showToast(`거래처 매핑 '${newMapping.companyName}'이(가) 등록되었습니다.`);
  }, []);

  // 거래처 사전 일괄 추가 (중복 자동 제거)
  const handleAddBatchCompanyMappings = useCallback((newMappings: CompanyMapping[]) => {
    setCompanyMappings((prev) => {
      const { mergedList, addedCount } = mergeCompanyMappings(prev, newMappings);
      showToast(`신규 거래처 ${addedCount}건이 매핑 사전에 안전하게 추가되었습니다!`);
      return mergedList;
    });
  }, []);

  const handleDeleteCompanyMapping = useCallback((index: number) => {
    setCompanyMappings((prev) => prev.filter((_, i) => i !== index));
    showToast('거래처 매핑 항목이 삭제되었습니다.', 'info');
  }, []);

  // 입금자 사전 단건 추가
  const handleAddDepositorMapping = useCallback((newMapping: DepositorMapping) => {
    setDepositorMappings((prev) => {
      const { mergedList } = mergeDepositorMappings(prev, [newMapping], true);
      return mergedList;
    });
    showToast(`입금자 매핑 '${newMapping.depositorName}'이(가) 저장되었습니다.`);
  }, []);

  // 입금자 사전 일괄 추가 (중복 자동 제거)
  const handleAddBatchDepositorMappings = useCallback((newMappings: DepositorMapping[]) => {
    setDepositorMappings((prev) => {
      const { mergedList, addedCount } = mergeDepositorMappings(prev, newMappings);
      showToast(`신규 입금자 ${addedCount}건이 매핑 사전에 안전하게 추가되었습니다!`);
      return mergedList;
    });
  }, []);

  const handleDeleteDepositorMapping = useCallback((index: number) => {
    setDepositorMappings((prev) => prev.filter((_, i) => i !== index));
    showToast('입금자 매핑 항목이 삭제되었습니다.', 'info');
  }, []);

  // 저장된 모든 데이터 초기화 모달 열기
  const handleClearAllData = useCallback(() => {
    setIsClearModalOpen(true);
  }, []);

  // 저장 데이터 초기화 실행 핸들러
  const handleExecuteClear = useCallback(
    (targets: ClearDataTargets) => {
      const clearedNames: string[] = [];

      if (targets.trainings) {
        setTrainings([]);
        localStorage.removeItem(STORAGE_KEYS.TRAININGS);
        clearedNames.push('훈련내역');
      }

      if (targets.invoices) {
        setInvoices([]);
        localStorage.removeItem(STORAGE_KEYS.INVOICES);
        clearedNames.push('계산서발행내역');
      }

      if (targets.deposits) {
        setDeposits([]);
        localStorage.removeItem(STORAGE_KEYS.DEPOSITS);
        clearedNames.push('입금내역');
      }

      if (targets.userEditsAndExpenses) {
        setUserEditedRows(new Map());
        setExpenseMap({});
        localStorage.removeItem(STORAGE_KEYS.USER_EDITED_ROWS);
        localStorage.removeItem(STORAGE_KEYS.EXPENSE_MAP);
        clearedNames.push('비용신청 체크/수정내역');
      }

      if (targets.companyMappings) {
        setCompanyMappings([]);
        localStorage.removeItem(STORAGE_KEYS.COMPANY_MAPPINGS);
        clearedNames.push('거래처 매핑 사전');
      }

      if (targets.depositorMappings) {
        setDepositorMappings([]);
        localStorage.removeItem(STORAGE_KEYS.DEPOSITOR_MAPPINGS);
        clearedNames.push('입금자 매핑 사전');
      }

      if (clearedNames.length > 0) {
        showToast(`🗑️ ${clearedNames.join(', ')}이(가) 성공적으로 초기화되었습니다.`, 'info');
      }
    },
    []
  );

  return (
    <div
      id="workspace-app"
      className={`min-h-screen bg-slate-100 text-slate-900 flex flex-col font-sans ${isManualModalOpen ? 'team-manual-open' : ''}`}
    >
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        totalCount={integratedData.length}
        needReviewCount={needReviewCount}
        depositCount={deposits.length}
        onExportExcel={handleExportExcel}
        onRefreshSharedFolder={handleRefreshSharedFolder}
        onConnectDirectory={handleConnectDirectory}
        onOpenManual={() => setIsManualModalOpen(true)}
        isRefreshing={isRefreshing}
        lastSyncTime={sharedFolderInfo.lastSyncTime}
        centers={centers}
        activeCenterId={center.id}
        onChangeCenter={onChangeCenter}
        onEditCenter={onEditCenter}
        onAddCenter={onAddCenter}
      />

      {/* Floating Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 animate-bounce-short">
          <div
            className={`flex items-center space-x-2.5 px-4 py-3 rounded-xl shadow-lg border text-xs font-medium ${
              notification.type === 'success'
                ? 'bg-emerald-900 text-white border-emerald-700'
                : notification.type === 'error'
                ? 'bg-rose-900 text-white border-rose-700'
                : 'bg-slate-900 text-white border-slate-700'
            }`}
          >
            {notification.type === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
            {notification.type === 'error' && <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />}
            {notification.type === 'info' && <FolderSync className="w-4 h-4 text-blue-400 shrink-0" />}
            <span>{notification.message}</span>
            <button
              onClick={() => setNotification(null)}
              className="ml-2 text-slate-300 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      <main className="flex-1 w-full px-2 sm:px-4 lg:px-6 py-4">
        {activeTab === 'data' && (
          <DataSheetView
            data={integratedData}
            onUpdateRow={handleUpdateRow}
            onExportExcel={handleExportExcel}
            onNavigateToMappings={() => setActiveTab('mappings')}
            onOpenClaimTab={() => setActiveTab('claim')}
            onRefreshSharedFolder={handleRefreshSharedFolder}
            onConnectDirectory={handleConnectDirectory}
            isRefreshing={isRefreshing}
            lastSyncTime={sharedFolderInfo.lastSyncTime}
            onShowToast={showToast}
            companyMappings={companyMappings}
            depositorMappings={depositorMappings}
            invoices={invoices}
            deposits={deposits}
            onAddCompanyMapping={handleAddCompanyMapping}
            onAddDepositorMapping={handleAddDepositorMapping}
          />
        )}

        {activeTab === 'deposit-invoice' && (
          <DepositInvoiceView
            deposits={deposits}
            invoices={invoices}
            companyMappings={companyMappings}
            depositorMappings={depositorMappings}
            trainings={trainings}
            onNavigateToUpload={() => setActiveTab('upload')}
            onAddCompanyMapping={handleAddCompanyMapping}
            onAddDepositorMapping={handleAddDepositorMapping}
            onShowToast={showToast}
          />
        )}

        {activeTab === 'claim' && <RpaClaimView onShowToast={showToast} />}

        {activeTab === 'upload' && (
          <UploadManager
            onDataLoaded={handleDataLoaded}
            trainingsCount={trainings.length}
            companyMappingsCount={companyMappings.length}
            depositorMappingsCount={depositorMappings.length}
            invoicesCount={invoices.length}
            depositsCount={deposits.length}
            onGoToDataSheet={() => setActiveTab('data')}
            sharedFolderInfo={sharedFolderInfo}
            onConnectDirectory={handleConnectDirectory}
            onRefreshSharedFolder={handleRefreshSharedFolder}
            onUpdateSharedPath={handleUpdateSharedPath}
            isRefreshing={isRefreshing}
            directoryHandleConnected={!!directoryHandle}
            onClearAllData={handleClearAllData}
          />
        )}

        {activeTab === 'mappings' && (
          <MappingDictionaryView
            trainings={trainings}
            invoices={invoices}
            deposits={deposits}
            companyMappings={companyMappings}
            depositorMappings={depositorMappings}
            onAddCompanyMapping={handleAddCompanyMapping}
            onAddBatchCompanyMappings={handleAddBatchCompanyMappings}
            onDeleteCompanyMapping={handleDeleteCompanyMapping}
            onAddDepositorMapping={handleAddDepositorMapping}
            onAddBatchDepositorMappings={handleAddBatchDepositorMappings}
            onDeleteDepositorMapping={handleDeleteDepositorMapping}
          />
        )}
      </main>

      <footer className="bg-white border-t border-slate-200 py-4 text-center text-xs text-slate-500">
        <p>수주 및 비용 통합 관리 시스템 · 훈련비 청구/계산서/입금/정부지원금 자동 매핑 프로그램</p>
      </footer>

      {/* 사내 공용폴더 연동 관리 모달 */}
      <ConnectSharedFolderModal
        isOpen={isConnectModalOpen}
        onClose={() => setIsConnectModalOpen(false)}
        sharedFolderInfo={sharedFolderInfo}
        onUpdateSharedPath={handleUpdateSharedPath}
        onDataLoaded={handleDataLoaded}
        onSyncComplete={handleModalSyncComplete}
      />

      {/* 저장 데이터 초기화 관리 모달 */}
      <ClearDataModal
        isOpen={isClearModalOpen}
        onClose={() => setIsClearModalOpen(false)}
        trainingsCount={trainings.length}
        invoicesCount={invoices.length}
        depositsCount={deposits.length}
        companyMappingsCount={companyMappings.length}
        depositorMappingsCount={depositorMappings.length}
        hasUserEdits={userEditedRows.size > 0}
        hasExpenseChecks={Object.keys(expenseMap).length > 0}
        onExecuteClear={handleExecuteClear}
      />

      {/* 비전공자 팀원 설명서 및 PDF 인쇄 모달 */}
      <TeamManualModal
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
      />
    </div>
  );
}
