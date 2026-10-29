import React from 'react';
import { COMPANY_STATES, CompanyState, formatMoney, hasEvidence, RpaBusiness, selectable } from './types';

interface CompanyTableProps {
  businesses: RpaBusiness[];
  picked: Set<string>;
  compact: boolean;
  onToggle: (key: string) => void;
  onState: (business: RpaBusiness, state: CompanyState) => void;
  onOpen: (business: RpaBusiness) => void;
  openKey: string;
}

const stateColor: Record<CompanyState, string> = {
  신청가능: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  신청완료: 'border-indigo-300 bg-indigo-50 text-indigo-800',
  불가: 'border-rose-300 bg-rose-50 text-rose-700',
};

const EvidenceCell: React.FC<{ file: string }> = ({ file }) => (
  <span className={file ? 'text-emerald-700' : 'text-amber-600'} title={file}>
    {file ? `✓ ${file}` : '대기'}
  </span>
);

// 관리번호를 어디서 얻었는지 — 추정(사업자번호+0)은 실행 때 HRD-Net 목록의 업체명으로 한 번 더 확인한다
const NumberSource: React.FC<{ source: string }> = ({ source }) => {
  if (!source || source === '엑셀') return null;
  const style = source === '확인됨' ? 'bg-emerald-100 text-emerald-800'
    : source === '추정' ? 'bg-sky-100 text-sky-800' : 'bg-amber-100 text-amber-800';
  const label = source === '추정' ? '추정' : source === '확인됨' ? '확인됨' : '확인필요';
  const hint = source === '추정' ? '사업자번호 뒤에 0을 붙인 값 — 실행 때 업체명으로 확인'
    : source === '확인됨' ? 'HRD-Net 목록에서 확인한 번호' : `${source} — 실행 때 목록에서 업체명으로 찾음`;
  return <span className={`ml-1 rounded px-1 font-sans text-[10px] font-semibold ${style}`} title={hint}>{label}</span>;
};

// 회차를 펼치면 나오는 업체 표 — 체크(신청가능만) · 상태 콤보 · 맨 오른쪽 ▸ 세로 현황
export const CompanyTable: React.FC<CompanyTableProps> = ({ businesses, picked, compact, onToggle, onState, onOpen, openKey }) => {
  if (businesses.length === 0) {
    return <p className="text-slate-400">사업장 상세 데이터가 없습니다. RPA 엔진을 다시 실행해 주세요.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className={`w-full text-left text-[11px] ${compact ? 'min-w-[560px]' : 'min-w-[980px]'}`}>
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="w-8 px-2 py-2" />
            <th className="px-2 py-2">번호</th>
            <th className="px-2 py-2">업체명</th>
            {!compact && <th className="px-2 py-2">사업장관리번호</th>}
            {!compact && <th className="px-2 py-2 text-right">훈련인원</th>}
            <th className="px-2 py-2 text-right">신청금액</th>
            {!compact && <th className="px-2 py-2">전자계산서</th>}
            {!compact && <th className="px-2 py-2">수납확인서</th>}
            <th className="px-2 py-2">상태</th>
            <th className="px-2 py-2">최근 결과</th>
            <th className="w-8 px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {businesses.map((b, index) => {
            const can = selectable(b);
            const why = b.제외사유 ? b.자동사유 : b.사유 || b.자동사유 || b.증빙확인;
            return (
              <tr key={b.key} className={`border-t border-slate-100 ${openKey === b.key ? 'bg-amber-50' : ''} ${b.제외사유 ? 'text-slate-400' : ''}`}>
                <td className="px-2 py-1.5">
                  <input type="checkbox" disabled={!can} checked={can && picked.has(b.key)} onChange={() => onToggle(b.key)}
                    title={can ? '이 업체를 실행 대상으로' : '신청가능이고 증빙 2개가 다 있어야 고를 수 있습니다'} />
                </td>
                <td className="px-2 py-1.5 text-slate-400">{index + 1}</td>
                <td className="max-w-[14rem] truncate px-2 py-1.5 font-semibold text-slate-800" title={b.사업장명}>{b.사업장명 || '-'}</td>
                {!compact && (
                  <td className="px-2 py-1.5 font-mono text-slate-600" title={b.사업자번호 ? `사업자번호 ${b.사업자번호}` : ''}>
                    {b.사업장관리번호 || '-'}
                    <NumberSource source={b.관리번호출처} />
                  </td>
                )}
                {!compact && <td className="px-2 py-1.5 text-right">{Number(b.훈련인원 || 0).toLocaleString('ko-KR')}명</td>}
                <td className="px-2 py-1.5 text-right font-semibold">{formatMoney(b.신청금액)}</td>
                {!compact && <td className="max-w-[12rem] truncate px-2 py-1.5">{b.제외사유 ? '-' : <EvidenceCell file={b.전자계산서} />}</td>}
                {!compact && <td className="max-w-[12rem] truncate px-2 py-1.5">{b.제외사유 ? '-' : <EvidenceCell file={b.수납확인서} />}</td>}
                <td className="px-2 py-1.5">
                  <div className="flex items-center gap-1">
                    <select value={b.상태} onChange={(e) => onState(b, e.target.value as CompanyState)}
                      className={`rounded border px-1 py-0.5 text-[11px] font-semibold ${stateColor[b.상태]}`}>
                      {COMPANY_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                    {b.제외사유
                      ? <span className="rounded bg-slate-100 px-1 text-[10px] font-semibold text-slate-600" title="통합 DATA 시트에서 비용신청 대상이 아닌 행">제외 · {b.제외사유}</span>
                      : !hasEvidence(b) && <span className="rounded bg-amber-100 px-1 text-[10px] font-semibold text-amber-800">증빙 대기</span>}
                  </div>
                  {why && <div className="mt-0.5 max-w-[16rem] truncate text-[10px] text-slate-500" title={why}>{why}</div>}
                </td>
                <td className="max-w-[9rem] truncate px-2 py-1.5 text-slate-600" title={b.f09 || b.f08}>
                  {b.f08 ? `${b.f08}${b.f06 ? ` · ${b.f06}` : ''}` : '-'}
                </td>
                <td className="px-2 py-1.5">
                  <button type="button" onClick={() => onOpen(b)} title="세로 현황 보기"
                    className="rounded px-1.5 py-0.5 font-bold text-indigo-700 hover:bg-indigo-100">▸</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
