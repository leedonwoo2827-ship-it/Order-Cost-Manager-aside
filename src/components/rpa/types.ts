// HRD-Net 비용신청 탭 — rpa 엔진(/api/state, /api/macros)이 주는 모양

export type CompanyState = '신청가능' | '신청완료' | '불가';
export const COMPANY_STATES: CompanyState[] = ['신청가능', '신청완료', '불가'];

// 업체(사업장) 한 줄. f01~f30 은 여분 필드(어떤 매크로로 어디까지 갔는지) — 뜻은 /api/macros 의 slots
export interface RpaBusiness {
  key: string;
  사업장명: string;
  사업장관리번호: string;
  관리번호출처: string;   // 엑셀 | 확인됨 | 추정(사업자번호+0) | 확인필요(유한회사 등)
  사업자번호: string;
  훈련인원: number;
  신청금액: number;
  전자계산서: string;
  수납확인서: string;
  증빙확인: string;
  제외사유?: string;     // 대시보드에서 대상이 아닌 행(입금 미확인·부분입금·비용신청 완료) — 업체 수를 맞추려고 같이 온다
  상태: CompanyState;
  사유: string;
  자동사유: string;
  수정: string;
  [field: `f${number}`]: string;
}

export interface RpaRound {
  folder: string;
  과정명: string;
  회차: string;
  사업장: number;
  사업장내역: RpaBusiness[];
  신청가능: number;
  증빙대기: number;
  제외?: Record<string, number>;   // 제외사유별 업체 수
  첨부: string[];
  정리: string;
  올리기: string;
  매크로: string;
  오류: string;
}

export interface RpaRun {
  과정명: string;
  회차: string;
  모드: string;
  상태: string;
  매크로?: string;
  자동: number;
  사람: number;
  못찾음: number;
  끝?: string;
}

export interface RpaState {
  busy: boolean;
  label: string;
  hrdnet: string[];
  kpi: Record<string, number>;
  rounds: RpaRound[];
  runs: RpaRun[];
  macro: string;
}

export interface RpaMacro {
  id: string;
  표시명: string;
  설명: string;
  원본: string;
  생성일: string;
  상태: '사용' | '시험중';
}

export interface RpaMode {
  id: 'simulate' | 'dry-run' | 'fill' | 'live';
  label: string;
  hint: string;
  flag: string;
}

export interface RpaMacros {
  macros: RpaMacro[];
  current: string;
  default: string;
  modes: RpaMode[];
  slots: Record<string, string>;
}

export const hasEvidence = (b: RpaBusiness) => Boolean(b.전자계산서 && b.수납확인서);
export const selectable = (b: RpaBusiness) => b.상태 === '신청가능' && hasEvidence(b) && !b.제외사유;
export const formatMoney = (value: number) => `${Number(value || 0).toLocaleString('ko-KR')}원`;
