import React, { useEffect, useState } from 'react';
import { formatMoney, RpaBusiness } from './types';

interface StatusDrawerProps {
  business: RpaBusiness | null;
  roundLabel: string;
  slots: Record<string, string>;
  onClose: () => void;
  onSaveReason: (business: RpaBusiness, reason: string) => void;
}

const FIELDS = Array.from({ length: 30 }, (_, i) => `f${String(i + 1).padStart(2, '0')}` as `f${number}`);

// 업체 한 곳의 세로 현황 — 여분 필드 f01~f30 (매크로·모드·단계 기록)과 사유
export const StatusDrawer: React.FC<StatusDrawerProps> = ({ business, roundLabel, slots, onClose, onSaveReason }) => {
  const [reason, setReason] = useState('');
  useEffect(() => setReason(business?.사유 ?? ''), [business?.key, business?.사유]);
  if (!business) return null;

  const info = FIELDS.filter((f) => !slots[f] || slots[f] !== '단계 기록');
  const steps = FIELDS.filter((f) => slots[f] === '단계 기록' && business[f]);

  return (
    <aside className="fixed right-0 top-0 z-40 flex h-full w-[min(360px,92vw)] flex-col border-l border-slate-200 bg-white shadow-2xl">
      <div className="flex items-start justify-between border-b border-slate-200 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[11px] text-slate-500" title={roundLabel}>{roundLabel}</p>
          <h3 className="truncate text-sm font-bold text-slate-900" title={business.사업장명}>{business.사업장명}</h3>
          <p className="text-[11px] text-slate-500">
            관리번호 {business.사업장관리번호 || '없음'}{business.관리번호출처 && business.관리번호출처 !== '엑셀' ? ` (${business.관리번호출처})` : ''}
            {business.사업자번호 ? ` · 사업자 ${business.사업자번호}` : ''} · {business.훈련인원}명 · {formatMoney(business.신청금액)}
          </p>
        </div>
        <button type="button" onClick={onClose} className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="닫기">✕</button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 py-3 text-xs">
        <section>
          <h4 className="mb-1 font-bold text-slate-700">상태</h4>
          <p className="font-semibold">{business.상태}{business.수정 ? <span className="ml-2 font-normal text-slate-400">수정 {business.수정}</span> : null}</p>
          {(business.자동사유 || business.증빙확인) && <p className="mt-1 text-amber-700">{[business.자동사유, business.증빙확인].filter(Boolean).join(' · ')}</p>}
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="사유 (예: 수납 미납 → 다음 신청)"
            className="mt-2 w-full rounded border border-slate-300 px-2 py-1" />
          <button type="button" onClick={() => onSaveReason(business, reason)} disabled={reason === business.사유}
            className="mt-1 rounded border border-indigo-300 px-2 py-0.5 font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-40">
            사유 저장
          </button>
        </section>
        <section>
          <h4 className="mb-1 font-bold text-slate-700">자동화 기록</h4>
          <dl className="divide-y divide-slate-100 rounded border border-slate-200">
            {info.map((f) => (
              <div key={f} className="flex gap-2 px-2 py-1">
                <dt className="w-32 shrink-0 text-slate-500"><span className="font-mono text-[10px] text-slate-400">{f}</span> {slots[f] || '여분'}</dt>
                <dd className="min-w-0 break-words text-slate-800">{business[f] || <span className="text-slate-300">-</span>}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section>
          <h4 className="mb-1 font-bold text-slate-700">단계 (f13~f30)</h4>
          {steps.length === 0 ? <p className="text-slate-400">아직 실행 기록이 없습니다.</p> : (
            <ol className="space-y-0.5 border-l-2 border-indigo-200 pl-3">
              {steps.map((f) => {
                const [id, result] = business[f].split(':');
                const bad = /불가|실패|중단|오류/.test(result || '');
                return (
                  <li key={f} className="flex gap-2">
                    <span className="w-14 shrink-0 font-mono text-slate-500">{id}</span>
                    <span className={bad ? 'font-semibold text-rose-600' : result === '사람' ? 'text-amber-700' : 'text-slate-700'}>{result || '-'}</span>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
    </aside>
  );
};
