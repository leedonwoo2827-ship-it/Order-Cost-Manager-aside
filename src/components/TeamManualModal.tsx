import React, { useRef } from 'react';
import {
  X,
  Printer,
  FileText,
  CheckCircle2,
  Table,
  CreditCard,
  FolderSync,
  BookOpen,
  ArrowRight,
  HelpCircle,
  Sparkles,
  ShieldCheck,
  Zap,
  Info,
  Download,
  RefreshCw,
  Sliders,
  Trash2,
} from 'lucide-react';

interface TeamManualModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const TeamManualModal: React.FC<TeamManualModalProps> = ({ isOpen, onClose }) => {
  const printRef = useRef<HTMLDivElement>(null);

  if (!isOpen) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div
      id="team-manual-modal"
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150 print:p-0 print:bg-white print:static"
      onClick={onClose}
    >
      <div
        className="bg-white border border-slate-200 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] print:max-h-none print:border-none print:shadow-none print:w-full print:rounded-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 상단 액션 헤더 (인쇄 시 숨김) */}
        <div className="px-6 py-4 bg-slate-900 text-white border-b border-slate-800 flex items-center justify-between print:hidden">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center font-bold text-white shadow-xs">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold tracking-tight">
                  수주 및 비용 통합 관리 시스템 이용가이드
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  PDF 인쇄 최적화
                </span>
              </div>
              <p className="text-xs text-slate-400">
                복잡한 엑셀 수작업을 10초 만에 끝내는 업무 자동화 가이드북
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handlePrint}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-lg shadow-sm transition active:scale-98 cursor-pointer"
              title="A4 규격으로 인쇄하거나 PDF 파일로 저장합니다."
            >
              <Printer className="w-4 h-4" />
              <span>PDF로 저장 / 인쇄하기</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition cursor-pointer"
              title="닫기"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 설명서 본문 (스크롤 가능 / 인쇄 시 A4 전체 출력) */}
        <div
          ref={printRef}
          className="p-6 sm:p-10 overflow-y-auto space-y-8 text-slate-800 text-sm leading-relaxed scrollbar-thin print:overflow-visible print:p-0 print:space-y-6"
        >
          {/* 표지 및 개요 섹션 */}
          <div className="border-b border-slate-200 pb-6">
            <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-200 text-blue-800 text-xs font-bold mb-3">
              <Sparkles className="w-3.5 h-3.5 text-blue-600" />
              <span>업무 효율화 프로젝트 매뉴얼 (v2.2.3)</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-slate-950 tracking-tight">
              수주 및 비용 통합 관리 시스템 사용자 가이드
            </h1>
            <p className="text-sm text-slate-500 mt-2">
              본 문서는 실무 담당자가 시스템의 동작 원리와 메뉴별 핵심 기능을 100% 활용할 수 있도록 직관적으로 정리된 업무 매뉴얼입니다.
            </p>
          </div>

          {/* 1. 시스템 도입 배경과 핵심 목적 */}
          <section className="space-y-3">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center space-x-2 border-l-4 border-blue-600 pl-2.5">
              <span>1. 시스템 도입 배경 및 기대 효과</span>
            </h2>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-4 bg-rose-50/70 border border-rose-200 rounded-xl">
                <span className="text-xs font-bold text-rose-800 block mb-1.5">❌ 기존 방식의 문제점 (수작업)</span>
                <ul className="text-xs text-slate-700 space-y-1.5 list-disc list-inside">
                  <li>HRD 훈련내역, 국세청 세금계산서, 은행 통장 내역이 분산되어 수작업 대조</li>
                  <li>거래처명이 조금만 달라도(예: '카카오' vs '주식회사 카카오') VLOOKUP 오류 발생</li>
                  <li>누가 돈을 냈는지, 계산서가 제대로 끊겼는지 눈으로 대조하느라 매주 3~4시간 소모</li>
                </ul>
              </div>

              <div className="p-4 bg-emerald-50/70 border border-emerald-200 rounded-xl">
                <span className="text-xs font-bold text-emerald-800 block mb-1.5">✅ 시스템 도입 후 (원클릭 자동화)</span>
                <ul className="text-xs text-slate-700 space-y-1.5 list-disc list-inside">
                  <li>사내 공용폴더에 엑셀만 넣어두면 <strong>3대 원본을 100% 자동 병합·대조</strong></li>
                  <li>유사 상호명 자동 정규화 및 '매핑 사전'을 통해 <strong>매칭 성공률 98% 달성</strong></li>
                  <li>'완납', '미수금', '분할입금', '미발행'을 <strong>색상 배지로 한눈에 파악</strong></li>
                </ul>
              </div>
            </div>
          </section>

          {/* 2. 3대 원본 데이터의 이해 */}
          <section className="space-y-3">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center space-x-2 border-l-4 border-blue-600 pl-2.5">
              <span>2. 시스템이 다루는 3대 원본 데이터</span>
            </h2>
            <p className="text-xs text-slate-600">
              우리 시스템은 아래 3가지 엑셀 원본 데이터를 하나로 엮어주는 스마트 정산 허브 역할을 합니다.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
                <div className="flex items-center space-x-2 text-blue-700 font-bold text-xs">
                  <Table className="w-4 h-4" />
                  <span>① 훈련내역 (수주 장부)</span>
                </div>
                <p className="text-[11.5px] text-slate-600 leading-snug">
                  어떤 기업이 어떤 교육 과정(인원, 수강료)을 들었는지 기록된 기본 수주 원장
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
                <div className="flex items-center space-x-2 text-emerald-700 font-bold text-xs">
                  <FileText className="w-4 h-4" />
                  <span>② 계산서발행내역 (청구 장부)</span>
                </div>
                <p className="text-[11.5px] text-slate-600 leading-snug">
                  회계팀에서 거래처에 실제로 전자세금계산서를 발행한 일자, 승인번호, 공급가액 내역
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
                <div className="flex items-center space-x-2 text-amber-700 font-bold text-xs">
                  <CreditCard className="w-4 h-4" />
                  <span>③ 입금내역 (통장 수금 장부)</span>
                </div>
                <p className="text-[11.5px] text-slate-600 leading-snug">
                  법인 계좌에 실제 입금된 거래 일자, 입금자명, 입금 금액 내역
                </p>
              </div>
            </div>
          </section>

          {/* 3. 메뉴별 핵심 기능 안내 */}
          <section className="space-y-4">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center space-x-2 border-l-4 border-blue-600 pl-2.5">
              <span>3. 주요 메뉴별 기능 및 사용 방법</span>
            </h2>

            {/* 메뉴 1 */}
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="w-6 h-6 rounded-lg bg-blue-600 text-white font-bold flex items-center justify-center text-xs">1</span>
                  <strong className="text-slate-900 text-sm font-bold">통합 DATA 시트</strong>
                </div>
                <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-[11px] font-semibold border border-blue-200">
                  전체 현황 종합 대시보드
                </span>
              </div>
              <p className="text-xs text-slate-600">
                훈련 수주 내역과 계산서 발행 내역이 자동으로 교차 매칭된 마스터 테이블입니다.
              </p>
              <ul className="text-xs text-slate-700 space-y-1 pl-4 list-disc">
                <li><strong>상태 배지 확인:</strong> [완납], [부분수금], [계산서미발행], [금액불일치] 등으로 자동 분류됩니다.</li>
                <li><strong>수납확인서 출력:</strong> 수금일자가 확인된 사업장·회차별 수납확인서를 미리보고, 개별 또는 일괄로 PDF 저장·인쇄할 수 있습니다.</li>
                <li><strong>비용신청 체크박스:</strong> 정산이 완료되어 비용을 신청할 건을 체크하면 브라우저에 실시간 영구 보존됩니다.</li>
                <li><strong>수동 메모 및 수정:</strong> 셀을 더블클릭하여 실무 메모나 비고를 직접 기록할 수 있으며 새로고침 후에도 유지됩니다.</li>
                <li><strong>엑셀 다운로드:</strong> 현재 정산 상태 그대로 완벽히 서식이 적용된 엑셀 보고서 파일(.xlsx)로 즉시 추출합니다.</li>
              </ul>
            </div>

            {/* 메뉴 2 */}
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="w-6 h-6 rounded-lg bg-emerald-600 text-white font-bold flex items-center justify-center text-xs">2</span>
                  <strong className="text-slate-900 text-sm font-bold">입금-계산서 대조</strong>
                </div>
                <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px] font-semibold border border-emerald-200">
                  통장 입금 vs 세금계산서 실시간 충당
                </span>
              </div>
              <p className="text-xs text-slate-600">
                통장에 들어온 돈이 어떤 세금계산서와 일치하는지 자동으로 충당 계산합니다.
              </p>
              <ul className="text-xs text-slate-700 space-y-1 pl-4 list-disc">
                <li><strong>1:1 완납 & 1:N 합산입금:</strong> 여러 건의 계산서를 한 번에 묶어서 송금한 경우도 금액 합산으로 자동 추적합니다.</li>
                <li><strong>수동 매핑 사전 연결 (강력 기능):</strong> 통장 입금자명이 낯설어 '미매핑'으로 뜬 경우, 클릭 한 번으로 거래처 사전이나 계산서에 강제 연결하면 즉시 완납 처리됩니다.</li>
              </ul>
            </div>

            {/* 메뉴 3 */}
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="w-6 h-6 rounded-lg bg-amber-600 text-white font-bold flex items-center justify-center text-xs">3</span>
                  <strong className="text-slate-900 text-sm font-bold">공용폴더 원본 관리</strong>
                </div>
                <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-700 text-[11px] font-semibold border border-amber-200">
                  사내 공용폴더 연동 & 파일 수동 업로드
                </span>
              </div>
              <p className="text-xs text-slate-600">
                실제 팀에서 사용하는 사내 공유 폴더나 네트워크 드라이브를 브라우저에 연결합니다.
              </p>
              <ul className="text-xs text-slate-700 space-y-1 pl-4 list-disc">
                <li><strong>공용폴더 새로고침:</strong> 상단 바의 [공용폴더 새로고침] 버튼을 누르면 폴더 안의 최신 엑셀을 1초 만에 다시 읽어옵니다.</li>
                <li><strong>저장 데이터 초기화:</strong> 3대 원본 비우기, 체크박스/메모/사전 초기화 등을 안전하게 선택하여 실행할 수 있습니다.</li>
              </ul>
            </div>

            {/* 메뉴 4 */}
            <div className="p-4 bg-white border border-slate-200 rounded-xl shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="w-6 h-6 rounded-lg bg-purple-600 text-white font-bold flex items-center justify-center text-xs">4</span>
                  <strong className="text-slate-900 text-sm font-bold">매핑 사전 관리</strong>
                </div>
                <span className="px-2 py-0.5 rounded bg-purple-50 text-purple-700 text-[11px] font-semibold border border-purple-200">
                  거래처명 & 입금자명 별칭 사전
                </span>
              </div>
              <p className="text-xs text-slate-600">
                훈련 상호명과 통장 입금자명이 다른 거래처의 별칭(Alias)을 관리합니다.
              </p>
              <ul className="text-xs text-slate-700 space-y-1 pl-4 list-disc">
                <li>한 번만 사전에 등록해 두면, 앞으로 들어오는 모든 엑셀 데이터에 평생 자동 적용됩니다.</li>
              </ul>
            </div>
          </section>

          {/* 4. 실무자를 위한 표준 업무 순서 (4단계) */}
          <section className="space-y-3">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center space-x-2 border-l-4 border-blue-600 pl-2.5">
              <span>4. 실무 표준 업무 플로우 (일일/월간 4단계)</span>
            </h2>

            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-center">
                <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                  <span className="text-[11px] font-bold text-blue-600 block mb-1">STEP 1</span>
                  <strong className="text-xs text-slate-900 block">공용폴더 동기화</strong>
                  <p className="text-[10.5px] text-slate-500 mt-1">상단 [공용폴더 새로고침] 클릭</p>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                  <span className="text-[11px] font-bold text-emerald-600 block mb-1">STEP 2</span>
                  <strong className="text-xs text-slate-900 block">미매핑 입금 해결</strong>
                  <p className="text-[10.5px] text-slate-500 mt-1">[수동 매핑]으로 거래처 연결</p>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                  <span className="text-[11px] font-bold text-amber-600 block mb-1">STEP 3</span>
                  <strong className="text-xs text-slate-900 block">비용신청 체크</strong>
                  <p className="text-[10.5px] text-slate-500 mt-1">완납된 수주건 체크박스 선택</p>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
                  <span className="text-[11px] font-bold text-purple-600 block mb-1">STEP 4</span>
                  <strong className="text-xs text-slate-900 block">보고용 엑셀 추출</strong>
                  <p className="text-[10.5px] text-slate-500 mt-1">[엑셀 다운로드]로 상신</p>
                </div>
              </div>
            </div>
          </section>

          {/* 5. 자주 묻는 질문 (FAQ) - 현재 실제 시스템 기능과 100% 일치 */}
          <section className="space-y-3">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 flex items-center space-x-2 border-l-4 border-blue-600 pl-2.5">
              <span>5. 자주 묻는 질문 (FAQ)</span>
            </h2>

            <div className="space-y-2.5 text-xs">
              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <strong className="text-slate-900 flex items-center space-x-1.5 font-bold">
                  <HelpCircle className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>Q. 제가 체크한 비용신청 체크박스나 수정 메모가 컴퓨터를 껐다 켜면 사라지나요?</span>
                </strong>
                <p className="text-slate-600 pl-5.5 leading-relaxed">
                  <strong>A. 사라지지 않습니다.</strong> 브라우저의 안전한 내부 저장소(LocalStorage)에 실시간 자동 저장되므로, 브라우저 창을 닫거나 컴퓨터를 재부팅해도 이전 작업 상태가 그대로 유지됩니다.
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <strong className="text-slate-900 flex items-center space-x-1.5 font-bold">
                  <HelpCircle className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>Q. [입금-계산서 대조] 화면에서 '미매핑'으로 뜨는 건 왜 그런가요?</span>
                </strong>
                <p className="text-slate-600 pl-5.5 leading-relaxed">
                  <strong>A. 통장에 찍힌 입금자명이 회사 상호와 다르거나 대표자 개인 이름으로 입금된 경우입니다.</strong><br />
                  이 경우 행 우측의 <strong>[수동 매핑]</strong> 버튼을 눌러 대상 거래처를 선택해주시면, 시스템이 즉시 해당 입금자명을 거래처 사전과 연결하여 <strong>[완납]</strong>으로 전환하고 다음부터는 자동으로 인식합니다.
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <strong className="text-slate-900 flex items-center space-x-1.5 font-bold">
                  <HelpCircle className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>Q. 사내 공용폴더에 새로운 엑셀 파일이 추가되었을 때는 어떻게 해야 하나요?</span>
                </strong>
                <p className="text-slate-600 pl-5.5 leading-relaxed">
                  <strong>A. 상단 네비게이션 바의 [공용폴더 새로고침] 버튼을 클릭하시면 됩니다.</strong><br />
                  버튼 클릭 즉시 연결된 폴더 내 3대 원본 엑셀을 다시 스캔하여 최신 내역으로 자동 병합·대조가 수행됩니다.
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <strong className="text-slate-900 flex items-center space-x-1.5 font-bold">
                  <HelpCircle className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>Q. 기존 샘플/테스트 데이터를 비우고 실제 회사 파일로 처음부터 시작하고 싶을 때는 어떻게 하나요?</span>
                </strong>
                <p className="text-slate-600 pl-5.5 leading-relaxed">
                  <strong>A. [공용폴더 원본 관리] 메뉴의 [저장 데이터 초기화] 버튼을 사용하시면 됩니다.</strong><br />
                  3대 원본 데이터 비우기, 비용신청 체크박스 초기화, 수동 수정 메모 초기화, 사용자 추가 매핑 사전 초기화 등 원하는 항목만 안전하게 선택하여 초기화할 수 있습니다.
                </p>
              </div>

              <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-1.5">
                <strong className="text-slate-900 flex items-center space-x-1.5 font-bold">
                  <HelpCircle className="w-4 h-4 text-blue-600 shrink-0" />
                  <span>Q. [엑셀 다운로드] 버튼으로 내려받는 파일은 어떤 형태인가요?</span>
                </strong>
                <p className="text-slate-600 pl-5.5 leading-relaxed">
                  <strong>A. 실무 결재 및 상신용으로 즉시 제출 가능한 스타일 서식 적용 엑셀 파일(.xlsx)입니다.</strong><br />
                  수주/계산서/입금 상세 컬럼과 함께 상태 배지 및 비용신청 체크 결과가 깔끔하게 정돈되어 다운로드됩니다.
                </p>
              </div>
            </div>
          </section>

          {/* 하단 푸터 서명 */}
          <div className="border-t border-slate-200 pt-5 text-center text-xs text-slate-400">
            <p>수주 및 비용 통합 관리 시스템 (Data Integration & Financial Matching Portal)</p>
            <p className="text-[11px] mt-0.5">운영팀 및 실무자를 위한 표준 기능 이용가이드</p>
          </div>
        </div>
      </div>
    </div>
  );
};
