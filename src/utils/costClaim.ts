import {CompanyMapping, IntegratedDataRow, InvoiceRecord} from '../types';
import {isPartialDeposit, isReceiptEligible} from './receiptDocument';

// 수금이 확인됐고 아직 비용신청하지 않은 행 = HRD-Net 비용신청 대상
export const isCostClaimTarget = (row: IntegratedDataRow) => isReceiptEligible(row) && !row.expenseApplied;

// 대상이 아닌 행이 빠지는 이유 — 비용신청 탭에서 '불가'로 보여 대시보드와 업체 수가 맞게 한다
export const costClaimExcludeReason = (row: IntegratedDataRow) => {
  if (row.expenseApplied) return '비용신청 완료';
  if (!(row.depositDate || '').trim()) return '입금 미확인';
  if (isPartialDeposit(row)) return '부분입금';
  return '';
};

const roundText = (value: number | string) => String(value ?? '').replace(/회차$/, '').trim();

const splitPeriod = (period: string) => {
  const dates = (period || '').match(/\d{4}-\d{2}-\d{2}/g) || [];
  return {start: dates[0] || '', end: dates[1] || dates[0] || ''};
};

export const roundKey = (course: string, round: number | string) => `${course.trim()}__${roundText(round)}`;

const digits = (value: string) => String(value || '').replace(/\D/g, '');
const nameKey = (value: string) =>
  String(value || '').replace(/주식회사|유한회사|\(주\)|㈜|\(유한\)|\(유\)/g, '').replace(/[^0-9A-Za-z가-힣]/g, '').toLowerCase();

// 사업자번호 찾기: 거래처코드 → (거래처 매핑, 계산서발행내역), 없으면 업체명.
// HRD-Net 사업장관리번호는 대개 사업자번호+0 이라 rpa 엔진이 이것으로 추정한다(유한회사 제외).
export function businessNumberLookup(companyMappings: CompanyMapping[] = [], invoices: InvoiceRecord[] = []) {
  const byCode = new Map<string, string>();
  const byName = new Map<string, string>();
  const add = (code: string, name: string, biz: string) => {
    const b = digits(biz);
    if (b.length !== 10) return;
    if (code && !byCode.has(code.trim())) byCode.set(code.trim(), b);
    if (name && !byName.has(nameKey(name))) byName.set(nameKey(name), b);
  };
  companyMappings.forEach((m) => {
    add(m.customerCode, m.companyName, m.businessNumber);
    add('', m.accountingName, m.businessNumber);
  });
  invoices.forEach((inv) => add(inv.customerCode, inv.customerName, inv.businessNumber));
  return (row: IntegratedDataRow) => byCode.get(String(row.customerCode || '').trim()) || byName.get(nameKey(row.companyName)) || '';
}

// 신청 대상 업체가 한 곳도 없어 비용신청 탭으로 안 넘어가는 회차 — '왜 12회차가 안 보이나'에 답하려고 올리기 확인창에 보여 준다
export function roundsWithoutTargets(data: IntegratedDataRow[]) {
  const byRound = new Map<string, {course: string; round: string; reasons: Record<string, number>; target: boolean}>();
  data.forEach((row) => {
    const key = roundKey(row.courseName, row.hrdRound);
    const r = byRound.get(key) || {course: row.courseName.trim(), round: roundText(row.hrdRound), reasons: {}, target: false};
    if (isCostClaimTarget(row)) r.target = true;
    else {
      const why = costClaimExcludeReason(row) || '기타';
      r.reasons[why] = (r.reasons[why] || 0) + 1;
    }
    byRound.set(key, r);
  });
  return [...byRound.values()]
    // 전부 '비용신청 완료'인 회차는 할 일이 없으니 빼고, 입금 대기 등이 남은 회차만
    .filter((r) => !r.target && r.round && Object.keys(r.reasons).some((k) => k !== '비용신청 완료'))
    .map((r) => ({...r, text: `${r.round}회차(${Object.entries(r.reasons).map(([k, n]) => `${k} ${n}`).join(', ')})`}));
}

// 증빙(전자계산서·수납확인서)은 사람이 rpa 증빙 폴더의 회차/업체 폴더에 직접 넣는다.
// 대상 행이 하나라도 있는 회차는 그 회차의 대시보드 행을 전부 보낸다 — 대상이 아닌 행은 제외사유를 달아서.
export function buildCostClaimPayload(
  data: IntegratedDataRow[],
  findBusinessNumber: (row: IntegratedDataRow) => string = () => '',
): RpaExportPayload {
  // v2.2.3: 대상 업체가 없어도 아직 할 일이 남은 회차(입금 미확인·부분입금 등, 반쯤 신청한 12회차 같은)도 보낸다 —
  // 비용신청 탭에서 '제외'로 보이고, 나중에 입금·납부된 업체는 사람이 상태 콤보를 '신청가능'으로 바꿔 돌린다
  const rounds = new Set([
    ...data.filter(isCostClaimTarget).map((row) => roundKey(row.courseName, row.hrdRound)),
    ...roundsWithoutTargets(data).map((r) => roundKey(r.course, r.round)),
  ]);
  const inRounds = data.filter((row) => rounds.has(roundKey(row.courseName, row.hrdRound)));
  const rows = inRounds.map((row) => {
    const {start, end} = splitPeriod(row.period);
    return {
      course: row.courseName.trim(),
      round: roundText(row.hrdRound),
      start,
      end,
      company: row.companyName.trim(),
      bizNo: findBusinessNumber(row),
      headcount: Number(row.headcount) || 0,
      amount: Number(row.govSubsidy) || 0,
      excludeReason: isCostClaimTarget(row) ? '' : costClaimExcludeReason(row),
    };
  });
  return {rows, receipts: []};
}
