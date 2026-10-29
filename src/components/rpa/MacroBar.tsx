import React from 'react';
import { RpaMacro, RpaMacros, RpaMode, RpaRun } from './types';

interface MacroBarProps {
  macros: RpaMacros | null;
  runs: RpaRun[];
  pickedCount: number;
  roundCount: number;
  disabled: boolean;
  onSelect: (id: string) => void;
  onStart: (mode: RpaMode) => void;
  onLearn: () => void;
  onClone: () => void;
  onPromote: (macro: RpaMacro) => void;
}

// 하단 — 매크로 고르기 + 모드 버튼 (모의 실행 · 점검 · 미리 채워 보기 · 신청) + 새 매크로 만들기
export const MacroBar: React.FC<MacroBarProps> = ({
  macros, runs, pickedCount, roundCount, disabled, onSelect, onStart, onLearn, onClone, onPromote,
}) => {
  const current = macros?.macros.find((m) => m.id === macros.current);
  const testing = current?.상태 === '시험중';
  const lastFill = runs.find((r) => r.매크로 === current?.id && (r.모드 === '미리채움' || r.모드 === '학습'));

  return (
    <div className="border-t border-slate-200 bg-slate-50 px-5 py-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="flex items-center gap-1 font-semibold text-slate-700">
          매크로
          <select value={macros?.current ?? ''} onChange={(e) => onSelect(e.target.value)} disabled={disabled || !macros}
            className="max-w-[18rem] rounded border border-slate-300 bg-white px-2 py-1 font-normal">
            {macros?.macros.map((m) => (
              <option key={m.id} value={m.id}>{m.표시명}{m.상태 === '시험중' ? ' (시험중)' : ''}</option>
            ))}
          </select>
        </label>
        {testing && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">시험중 — 신청 잠김</span>}
        <button type="button" onClick={onClone} disabled={disabled}
          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-40"
          title="지금 매크로를 복사해서 새 자동화를 시작합니다 (시험중으로 만들어짐)">
          ＋ 새 매크로
        </button>
        {testing && current && (
          <>
            <button type="button" onClick={onLearn} disabled={disabled}
              className="rounded-lg border border-teal-400 bg-white px-2.5 py-1 font-semibold text-teal-800 hover:bg-teal-50 disabled:opacity-40"
              title="업체 1곳만 골라, 모든 단계를 사람이 하며 클릭을 녹화합니다">
              학습 미리채워 보기
            </button>
            <button type="button" onClick={() => onPromote(current)} disabled={disabled}
              className="rounded-lg border border-indigo-300 bg-white px-2.5 py-1 font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-40">
              사용 승격
            </button>
          </>
        )}
        {lastFill && (
          <span className="text-[11px] text-slate-500">
            최근 {lastFill.모드}: 자동 {lastFill.자동} · <b className={lastFill.사람 ? 'text-amber-700' : 'text-emerald-700'}>사람 {lastFill.사람}</b> · 못찾음 {lastFill.못찾음}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">{pickedCount}개 업체 / {roundCount}개 회차 선택 →</span>
        {(macros?.modes ?? []).map((m) => (
          <button key={m.id} type="button" title={m.hint} onClick={() => onStart(m)}
            disabled={disabled || (m.id === 'live' && testing)}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold disabled:opacity-40 ${
              m.id === 'live' ? 'bg-indigo-700 text-white hover:bg-indigo-600'
              : m.id === 'fill' ? 'bg-teal-700 text-white hover:bg-teal-600'
              : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-100'}`}>
            {m.label}
          </button>
        ))}
      </div>
    </div>
  );
};
