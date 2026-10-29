import {CompanyMapping, IntegratedDataRow, InvoiceRecord} from '../types';
import {isReceiptEligible} from './receiptDocument';

// 수금이 확인됐고 아직 비용신청하지 않은 행 = HRD-Net 비용신청 대상
export const isCostClaimTarget = (row: IntegratedDataRow) => isReceiptEligible(row) && !row.expenseApplied;

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

// 증빙(전자계산서·수납확인서)은 사람이 rpa 증빙 폴더의 회차/업체 폴더에 직접 넣는다 — 여기서는 대상 행만 내보낸다
export function buildCostClaimPayload(
  data: IntegratedDataRow[],
  findBusinessNumber: (row: IntegratedDataRow) => string = () => '',
): RpaExportPayload {
  const targets = data.filter(isCostClaimTarget);
  const rows = targets.map((row) => {
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
    };
  });
  return {rows, receipts: []};
}
