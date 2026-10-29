import { IntegratedDataRow } from '../types';
import defaultReceiptStampDataUrl from '../assets/ubion-receipt-stamp.png?inline';

export interface ReceiptSettings {
  address: string;
  tel: string;
  fax: string;
  contact: string;
  issuer: string;
  employmentLabel: string;
  stampDataUrl: string;
}

export interface ReceiptGroup {
  key: string;
  companyName: string;
  round: string;
  rows: IntegratedDataRow[];
  fileName: string;
  latestDepositDate: string;
}

export const DEFAULT_RECEIPT_SETTINGS: ReceiptSettings = {
  address: '08378 서울시 구로구 디지털로34길 27(구로동) 대륭포스트타워3차 601호',
  tel: '02-2023-8865',
  fax: '02-2023-8799',
  contact: '교육운영팀 조성은',
  issuer: '㈜유비온 대표이사 임재환',
  employmentLabel: '고용',
  stampDataUrl: defaultReceiptStampDataUrl,
};

export const isPartialDeposit =(row: IntegratedDataRow) =>
  row.status === 'partial_deposit' || (row.note || '').includes('부분입금');

export const isReceiptEligible = (row: IntegratedDataRow) =>
  Boolean((row.depositDate || '').trim()) && !isPartialDeposit(row);

const cleanFilePart = (value: string) =>
  value.replace(/[\\/:*?"<>|]/g, ' ').replace(/\s+/g, ' ').trim();

const roundLabel = (value: number | string) => {
  const text = String(value ?? '').trim();
  if (!text) return '회차미상';
  return text.includes('회차') ? text : `${text}회차`;
};

export function groupReceiptRows(data: IntegratedDataRow[]): ReceiptGroup[] {
  const groups = new Map<string, ReceiptGroup>();

  data.filter(isReceiptEligible).forEach((row) => {
    const companyName = (row.companyName || '사업장명 미상').trim();
    const round = roundLabel(row.hrdRound);
    const key = `${companyName}__${round}`;
    const existing = groups.get(key);

    if (existing) {
      existing.rows.push(row);
      if ((row.depositDate || '') > existing.latestDepositDate) {
        existing.latestDepositDate = row.depositDate;
      }
      return;
    }

    groups.set(key, {
      key,
      companyName,
      round,
      rows: [row],
      fileName: `수납확인서_${cleanFilePart(companyName)}_${cleanFilePart(round)}.pdf`,
      latestDepositDate: row.depositDate || '',
    });
  });

  return Array.from(groups.values()).sort((a, b) =>
    b.latestDepositDate.localeCompare(a.latestDepositDate) ||
    a.companyName.localeCompare(b.companyName, 'ko', { numeric: true })
  );
}

const escapeHtml = (value: unknown) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

const formatMoney = (value: number) => Math.round(Number(value) || 0).toLocaleString('ko-KR');

const formatDate = (value: string) => {
  if (!value) return '-';
  const normalized = value.replace(/[./]/g, '-');
  const match = normalized.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (!match) return value;
  return `${match[1]}-${match[2].padStart(2, '0')}-${match[3].padStart(2, '0')}`;
};

const formatIssueMonth = (value: string) => {
  const normalized = value.replace(/[./]/g, '-');
  const match = normalized.match(/(\d{4})-(\d{1,2})/);
  if (match) return `${match[1]}.${match[2].padStart(2, '0')}`;
  const now = new Date();
  return `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, '0')}`;
};

const formatClaimMonth = (value: string) => {
  const match = String(value || '').match(/(\d{1,2})/);
  return match ? `${Number(match[1])}월` : value || '-';
};

export function buildReceiptHtml(group: ReceiptGroup, settings: ReceiptSettings): string {
  const issueMonth = formatIssueMonth(group.latestDepositDate);
  const totalHeadcount = group.rows.reduce((sum, row) => sum + (Number(row.headcount) || 0), 0);
  const totalCost = group.rows.reduce((sum, row) => sum + (Number(row.totalCost) || 0), 0);
  const stamp = settings.stampDataUrl
    ? `<img class="stamp" src="${escapeHtml(settings.stampDataUrl)}" alt="직인" />`
    : '';

  const rows = group.rows
    .map((row) => {
      const headcount = Number(row.headcount) || 0;
      const perPerson = headcount > 0 ? (Number(row.totalCost) || 0) / headcount : 0;
      return `<tr>
        <td>${escapeHtml(formatClaimMonth(row.claimMonth))}</td>
        <td class="course">${escapeHtml(row.courseName)}</td>
        <td>${escapeHtml(row.period || '-')}</td>
        <td>${escapeHtml(settings.employmentLabel || '고용')}</td>
        <td>${formatMoney(headcount)}</td>
        <td>${formatMoney(perPerson)}</td>
        <td>${formatMoney(Number(row.totalCost) || 0)}</td>
        <td>${escapeHtml(formatDate(row.invoiceDate))}</td>
        <td>${escapeHtml(formatDate(row.depositDate))}</td>
      </tr>`;
    })
    .join('');

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(group.fileName.replace(/\.pdf$/i, ''))}</title>
<style>
  @page { size: A4 landscape; margin: 0; }
  * { box-sizing: border-box; }
  html, body { width: 297mm; height: 210mm; margin: 0; background: #fff; }
  body { font-family: "Malgun Gothic", "Apple SD Gothic Neo", sans-serif; color: #111; }
  .page { width: 297mm; min-height: 210mm; padding: 16mm 20mm 13mm; position: relative; overflow: hidden; }
  .title { height: 9mm; background: #d3d3d3; display: flex; align-items: center; justify-content: center; font-size: 22pt; font-weight: 800; letter-spacing: 9px; }
  .company-line { margin-top: 9mm; font-size: 8.8pt; font-weight: 700; white-space: nowrap; }
  .divider { height: 3mm; margin-top: 1.5mm; background: #858585; }
  .meta { margin: 3mm 2mm 2mm; font-size: 9.5pt; line-height: 1.8; }
  .meta-label { display: inline-block; width: 23mm; letter-spacing: 4px; }
  .rule { border-top: 0.65mm solid #222; margin-top: 2mm; }
  .intro { margin: 4mm 0 4mm 11mm; font-size: 9.3pt; line-height: 1.65; }
  table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 8.3pt; }
  th { color: #fff; background: #050505; height: 7mm; font-weight: 700; }
  td { border-bottom: 0.25mm solid #c9c9c9; text-align: center; padding: 1.8mm 1mm; height: 7mm; }
  th:nth-child(1) { width: 7%; } th:nth-child(2) { width: 29%; } th:nth-child(3) { width: 20%; }
  th:nth-child(4) { width: 7%; } th:nth-child(5) { width: 6%; } th:nth-child(6) { width: 9%; }
  th:nth-child(7) { width: 10%; } th:nth-child(8) { width: 8.5%; } th:nth-child(9) { width: 8.5%; }
  td.course { text-align: left; padding-left: 2mm; }
  tfoot td { color: #fff; background: #050505; border: 0; font-weight: 800; height: 6.5mm; }
  .signature { position: relative; width: max-content; margin: 11mm auto 0; font-size: 17pt; font-weight: 800; letter-spacing: 6px; }
  .stamp { position: absolute; width: 21mm; height: 21mm; object-fit: contain; right: -12mm; top: -6mm; opacity: 0.9; }
  @media screen { body { transform-origin: top left; } }
</style>
</head>
<body>
  <section class="page">
    <div class="title">수 납 확 인 서</div>
    <div class="company-line">${escapeHtml(settings.address)} / TEL. ${escapeHtml(settings.tel)} / FAX. ${escapeHtml(settings.fax)} / 담당. ${escapeHtml(settings.contact)}</div>
    <div class="divider"></div>
    <div class="meta">
      <div><span class="meta-label">시행일자</span>: ${escapeHtml(issueMonth)}</div>
      <div><span class="meta-label">수　　신</span>: ${escapeHtml(group.companyName)} 교육담당자</div>
      <div><span class="meta-label">제　　목</span>: 온라인 교육비 수납확인서</div>
    </div>
    <div class="rule"></div>
    <div class="intro">
      <div>1. 귀사의 무궁한 발전을 기원합니다.</div>
      <div>2. ${escapeHtml(issueMonth.replace('.', '년 '))}월 온라인 교육비 수납을 다음과 같이 확인합니다.</div>
    </div>
    <table>
      <thead><tr><th>월</th><th>과정명</th><th>기간</th><th>고용여부</th><th>인원</th><th>교육비</th><th>총 교육비</th><th>계산서</th><th>입금일</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="4">합　계</td><td>${formatMoney(totalHeadcount)}</td><td></td><td>${formatMoney(totalCost)}</td><td colspan="2"></td></tr></tfoot>
    </table>
    <div class="signature">${escapeHtml(settings.issuer)}${stamp}</div>
  </section>
</body>
</html>`;
}
