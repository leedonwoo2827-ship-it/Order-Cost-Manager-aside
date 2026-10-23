import React, { useCallback, useEffect, useState } from 'react';
import { X } from 'lucide-react';

interface RpaRound {
  folder: string;
  과정명: string;
  회차: string;
  사업장: number;
  첨부: string[];
  정리: string;
  올리기: string;
  오류: string;
}

interface RpaState {
  busy: boolean;
  label: string;
  hrdnet: string[];
  kpi: Record<string, number>;
  rounds: RpaRound[];
}

type Mode = 'simulate' | 'dry-run' | 'fill' | 'live';

const MODES: { id: Mode; label: string; hint: string; flag: string }[] = [
  { id: 'simulate', label: '모의 실행', hint: 'HRD-Net 없이 순서만 훑기', flag: '--simulate' },
  { id: 'dry-run', label: '점검', hint: '화면에서 버튼을 찾기만 하고 누르지 않기', flag: '--dry-run' },
  { id: 'fill', label: '미리 채워 보기', hint: '최종 신청 직전까지 채우고 멈추기', flag: '--fill' },
  { id: 'live', label: '신청', hint: '실제 신청. 회차마다 패널에서 사람이 최종 확인', flag: '' },
];

interface RpaRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onShowToast?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

export const RpaRunModal: React.FC<RpaRunModalProps> = ({ isOpen, onClose, onShowToast }) => {
  const [state, setState] = useState<RpaState | null>(null);
  const [offline, setOffline] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    if (!window.rpaApi) return;
    const res = await window.rpaApi.call({ path: '/api/state' });
    if (res.ok && res.data) {
      setState(res.data as RpaState);
      setOffline(false);
    } else {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return undefined;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [isOpen, refresh]);

  if (!isOpen) return null;

  const rounds = state?.rounds ?? [];
  const ready = rounds.filter((r) => r.정리 === '준비완료');

  const run = async (args: string[], okMessage: string) => {
    if (!window.rpaApi) return;
    const res = await window.rpaApi.call({ method: 'POST', path: '/api/run', body: { args } });
    if (res.ok) onShowToast?.(okMessage, 'info');
    else onShowToast?.(res.error || '실행하지 못했습니다.', 'error');
    void refresh();
  };

  const organize = () => run(['organize'], '정리를 시작했습니다. 오른쪽 패널에서 진행을 볼 수 있어요.');

  const start = (mode: (typeof MODES)[number]) => {
    const folders = ready.filter((r) => picked.has(r.folder)).map((r) => r.folder);
    if (folders.length === 0) {
      onShowToast?.('실행할 회차를 체크하세요. (증빙누락 회차는 고를 수 없습니다)', 'info');
      return;
    }
    if (mode.id === 'live' && !window.confirm(`${folders.length}개 회차를 실제로 신청 진행합니다.\n회차마다 오른쪽 패널에서 최종 확인을 눌러야 신청됩니다.`)) return;
    const args = ['upload-all', `--only=${folders.join(',')}`];
    if (mode.flag) args.push(mode.flag);
    void run(args, `${mode.label}을 시작했습니다. 오른쪽 패널을 보세요.`);
  };

  const toggle = (folder: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(folder)) next.delete(folder);
      else next.add(folder);
      return next;
    });

  const allOn = ready.length > 0 && ready.every((r) => picked.has(r.folder));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">HRD-Net 비용신청 실행</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              회차를 고르고 단계를 누르세요. 진행과 질문(사람이 눌러야 할 곳)은 오른쪽 패널에 뜹니다.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-100" aria-label="닫기">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3 text-xs">
          <span className={`inline-flex items-center gap-1 ${state?.hrdnet.length ? 'text-emerald-700' : 'text-rose-600'}`}>
            ● {state?.hrdnet.length ? 'HRD-Net 창 있음' : 'HRD-Net 창 없음'}
          </span>
          <span className="text-slate-300">|</span>
          <span className={state?.busy ? 'text-amber-600' : 'text-emerald-700'}>
            ● {state?.busy ? `실행 중: ${state.label}` : '대기'}
          </span>
          {offline && <span className="text-rose-600">엔진에 연결되지 않았습니다. 「사이드 패널 열기」를 먼저 누르세요.</span>}
          <div className="ml-auto flex gap-2">
            <button type="button" onClick={organize} disabled={offline || state?.busy}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40">
              ▶ 정리 (내보낸 증빙을 회차별로 묶기)
            </button>
            <button type="button" onClick={() => void window.rpaApi?.call({ method: 'POST', path: '/api/stop', body: {} })}
              className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-1 font-semibold text-rose-700 hover:bg-rose-100">
              ■ 멈춤
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-5 py-3">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="w-8 py-2">
                  <input type="checkbox" checked={allOn}
                    onChange={() => setPicked(allOn ? new Set() : new Set(ready.map((r) => r.folder)))} />
                </th>
                <th className="py-2">과정</th>
                <th className="py-2">회차</th>
                <th className="py-2">사업장</th>
                <th className="py-2">증빙</th>
                <th className="py-2">정리</th>
                <th className="py-2">올리기 결과</th>
              </tr>
            </thead>
            <tbody>
              {rounds.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-400">
                    아직 정리된 회차가 없습니다. 위의 「▶ 정리」를 누르세요.
                  </td>
                </tr>
              )}
              {rounds.map((r) => {
                const ok = r.정리 === '준비완료';
                return (
                  <tr key={r.folder} className="border-b border-slate-100">
                    <td className="py-1.5">
                      <input type="checkbox" disabled={!ok} checked={picked.has(r.folder)} onChange={() => toggle(r.folder)} />
                    </td>
                    <td className="max-w-[18rem] truncate py-1.5" title={r.과정명}>{r.과정명}</td>
                    <td className="py-1.5">{r.회차}</td>
                    <td className="py-1.5">{r.사업장}곳</td>
                    <td className="py-1.5">{r.첨부.join(' · ') || '-'}</td>
                    <td className={`py-1.5 font-semibold ${ok ? 'text-emerald-700' : 'text-rose-600'}`}>{r.정리}</td>
                    <td className="py-1.5" title={r.오류}>{r.올리기}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rounds.some((r) => r.정리 === '증빙누락') && (
            <p className="mt-2 text-[11px] text-rose-600">
              증빙누락 회차는 전자계산서 PDF가 없습니다. 위하고 출력본을 증빙 폴더에 넣고 「▶ 정리」를 다시 누르세요.
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <span className="text-xs text-slate-500">{picked.size}개 회차 선택 →</span>
          {MODES.map((m) => (
            <button key={m.id} type="button" title={m.hint} onClick={() => start(m)} disabled={offline || state?.busy}
              className={`rounded-lg px-3 py-1.5 text-xs font-bold disabled:opacity-40 ${
                m.id === 'live' ? 'bg-indigo-700 text-white hover:bg-indigo-600'
                : m.id === 'fill' ? 'bg-teal-700 text-white hover:bg-teal-600'
                : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-100'}`}>
              {m.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
