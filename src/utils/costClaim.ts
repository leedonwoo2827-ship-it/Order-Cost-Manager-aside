import {IntegratedDataRow} from '../types';
import {buildReceiptHtml, DEFAULT_RECEIPT_SETTINGS, groupReceiptRows, isReceiptEligible, ReceiptSettings} from './receiptDocument';

// 수금이 확인됐고 아직 비용신청하지 않은 행 = HRD-Net 비용신청 대상
export const isCostClaimTarget = (row: IntegratedDataRow) => isReceiptEligible(row) && !row.expenseApplied;

const roundText = (value: number | string) => String(value ?? '').replace(/회차$/, '').trim();

const splitPeriod = (period: string) => {
  const dates = (period || '').match(/\d{4}-\d{2}-\d{2}/g) || [];
  return {start: dates[0] || '', end: dates[1] || dates[0] || ''};
};

export const roundKey = (course: string, round: number | string) => `${course.trim()}__${roundText(round)}`;

export function buildCostClaimPayload(
  data: IntegratedDataRow[],
  settings: ReceiptSettings = DEFAULT_RECEIPT_SETTINGS,
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
      headcount: Number(row.headcount) || 0,
      amount: Number(row.govSubsidy) || 0,
    };
  });
  const receipts = groupReceiptRows(targets).map((group) => ({
    course: group.rows[0].courseName.trim(),
    round: group.round,
    fileName: group.fileName,
    html: buildReceiptHtml(group, settings),
  }));
  return {rows, receipts};
}
