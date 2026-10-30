import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CompanyTable } from './rpa/CompanyTable';
import { MacroBar } from './rpa/MacroBar';
import { StatusDrawer } from './rpa/StatusDrawer';
import {
  CompanyState, COMPANY_STATES, hasEvidence, RpaBusiness, RpaMacro, RpaMacros, RpaMode, RpaRound, RpaState, selectable,
} from './rpa/types';

interface BackupItem {
  name: string;
  path: string;
  시각: string;
  회차: { folder: string; 회차: string; 사업장: number; 신청금액: number; 상태: string; 끝: string }[];
  파일: number;
  MB: number;
  장기보관: boolean;
  삭제예정: string;
}

interface BackupList {
  root: string;
  keep_days: number;
  archive_root: string;
  items: BackupItem[];
}

type Filter = '전체' | CompanyState | '증빙대기';

interface RpaClaimViewProps {
  onShowToast?: (message: string, type?: 'success' | 'error' | 'info') => void;
}

export const RpaClaimView: React.FC<RpaClaimViewProps> = ({ onShowToast }) => {
  const [state, setState] = useState<RpaState | null>(null);
  const [macros, setMacros] = useState<RpaMacros | null>(null);
  const [offline, setOffline] = useState(false);
  const [backups, setBackups] = useState<BackupList | null>(null);
  const [withTest, setWithTest] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());      // 업체 status 키
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [openKey, setOpenKey] = useState('');
  const [filter, setFilter] = useState<Filter>('전체');
  const [query, setQuery] = useState('');
  const [compact, setCompact] = useState(false);

  const refresh = useCallback(async () => {
    if (!window.rpaApi) return;
    const res = await window.rpaApi.call({ path: '/api/state' });
    if (res.ok && res.data) {
      setState(res.data as RpaState);
      setOffline(false);
      const bk = await window.rpaApi.call({ path: '/api/backups' });
      if (bk.ok && bk.data) setBackups(bk.data as BackupList);
    } else {
      setOffline(true);
    }
  }, []);

  const loadMacros = useCallback(async () => {
    const res = await window.rpaApi?.call({ path: '/api/macros' });
    if (res?.ok && res.data) setMacros(res.data as RpaMacros);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!offline) void loadMacros();
  }, [offline, loadMacros]);

  // 모니터 1개면 대시보드가 화면 오른쪽 아래로 작아진다 → 축소 보기
  useEffect(() => window.rpa?.onLayout((info) => setCompact(info.compact)), []);

  const rounds = state?.rounds ?? [];
  const byKey = useMemo(() => {
    const m = new Map<string, { business: RpaBusiness; round: RpaRound }>();
    rounds.forEach((round) => round.사업장내역.forEach((business) => m.set(business.key, { business, round })));
    return m;
  }, [rounds]);

  // 사람이 콤보로 불가/신청완료로 바꾸거나 증빙이 빠지면 선택에서 뺀다
  useEffect(() => {
    setPicked((prev) => {
      const next = new Set([...prev].filter((k) => byKey.has(k) && selectable(byKey.get(k)!.business)));
      return next.size === prev.size ? prev : next;
    });
  }, [byKey]);

  const matches = useCallback((b: RpaBusiness, r: RpaRound) => {
    if (filter === '증빙대기' && (hasEvidence(b) || b.제외사유)) return false;
    if (filter !== '전체' && filter !== '증빙대기' && b.상태 !== filter) return false;
    const q = query.trim();
    return !q || b.사업장명.includes(q) || b.사업장관리번호.includes(q) || r.과정명.includes(q) || `${r.회차}회차`.includes(q);
  }, [filter, query]);

  const visible = useMemo(
    () => rounds
      .map((r) => ({ round: r, businesses: r.사업장내역.filter((b) => matches(b, r)) }))
      .filter((v) => v.businesses.length > 0),
    [rounds, matches],
  );

  const call = async (path: RpaApiPath, body: unknown, okMessage = '') => {
    if (!window.rpaApi) return false;
    const res = await window.rpaApi.call({ method: 'POST', path, body });
    if (res.ok) {
      if (okMessage) onShowToast?.(okMessage, 'info');
    } else {
      onShowToast?.(res.error || '실행하지 못했습니다.', 'error');
    }
    void refresh();
    return res.ok;
  };
  const run = (args: string[], okMessage: string, companies?: string[]) =>
    call('/api/run', companies ? { args, companies } : { args }, okMessage);

  const openPanel = async () => {
    const res = await window.rpa?.launch();
    if (res?.layout) setCompact(res.layout.compact);
    onShowToast?.(res?.ok ? '사이드 패널을 열고 창을 배치했습니다.' : res?.reason || '사이드 패널을 열지 못했습니다.', res?.ok ? 'success' : 'error');
    void refresh();
  };

  const relayout = async () => {
    const res = await window.rpa?.layout();
    if (res?.layout) setCompact(res.layout.compact);
    onShowToast?.(res?.ok ? `창을 다시 배치했습니다 (${res.layout?.mode === 'dual' ? '듀얼 모니터' : '한 화면'}).` : res?.reason || '배치하지 못했습니다.', res?.ok ? 'success' : 'error');
  };

  const makeResult = async () => {
    await run(['result'], '결과표를 만들었습니다. 잠시 뒤 결과 폴더가 열립니다.');
    window.setTimeout(() => void window.rpa?.openResults(), 3000);
  };

  const backup = async (includeTest: boolean) => {
    const what = includeTest ? '신청 성공 + 모의·점검·채움까지 끝난' : '신청 성공한';
    if (!window.confirm(`${what} 회차의 파일을 백업 폴더로 옮깁니다.
지우지 않고 옮기기만 하며, 결과표와 아직 안 끝난 회차는 그대로 둡니다.`)) return;
    await run(includeTest ? ['backup', '--include-test'] : ['backup'], '백업을 시작했습니다. 잠시 뒤 백업 폴더가 열립니다.');
    window.setTimeout(() => void window.rpa?.openBackup(), 3000);
  };

  const organize = () => run(['organize'], '정리를 시작했습니다. 증빙 폴더에 회차 > 업체 폴더가 만들어집니다.');

  const pickedRounds = useMemo(
    () => rounds.filter((r) => r.사업장내역.some((b) => picked.has(b.key))).map((r) => r.folder),
    [rounds, picked],
  );

  const start = (mode: RpaMode) => {
    if (picked.size === 0) {
      onShowToast?.('실행할 업체를 체크하세요. (신청가능이고 증빙 2개가 다 있는 업체만 고를 수 있습니다)', 'info');
      return;
    }
    if (mode.id === 'live' && !window.confirm(`${pickedRounds.length}개 회차 · ${picked.size}개 업체를 실제로 신청 진행합니다.
회차마다 묻지 않고 끝까지 이어서 [훈련비용 신청]까지 누릅니다. 진행할까요?`)) return;
    const args = ['upload-all', `--only=${pickedRounds.join(',')}`, `--macro=${macros?.current ?? ''}`];
    if (mode.flag) args.push(mode.flag);
    // 연속 실행 — 고른 회차를 회차마다 묻지 않고 끝까지 (멈춘 회차는 화면을 정리하고 다음 회차로)
    if (mode.id === 'live' || mode.id === 'fill') args.push('--auto');
    void run(args, `${mode.label}을 시작했습니다. 오른쪽 패널을 보세요.`, [...picked]);
  };

  const learn = () => {
    if (picked.size !== 1) {
      onShowToast?.('학습 미리채워 보기는 업체 1곳만 체크해서 돌립니다.', 'info');
      return;
    }
    void run(['upload-all', `--only=${pickedRounds.join(',')}`, `--macro=${macros?.current ?? ''}`, '--learn'],
      '학습을 시작했습니다. 패널 안내대로 HRD-Net에서 직접 누르면 클릭이 녹화됩니다.', [...picked]);
  };

  const selectMacro = async (id: string) => {
    if (await call('/api/macros/select', { id })) void loadMacros();
  };

  const cloneMacro = async () => {
    const name = window.prompt('새 매크로 이름을 적어 주세요.\n지금 매크로를 복사해서 「시험중」으로 만듭니다. 업체 1곳으로 「학습 미리채워 보기」→「미리 채워 보기」로 확인한 뒤 「사용 승격」을 누르면 신청에 쓸 수 있습니다.');
    if (!name?.trim()) return;
    const res = await window.rpaApi?.call({ method: 'POST', path: '/api/macros/clone', body: { name, source: macros?.current } });
    if (!res?.ok) {
      onShowToast?.(res?.error || '만들지 못했습니다.', 'error');
      return;
    }
    await call('/api/macros/select', { id: res.data.macro.id }, `‘${res.data.macro.표시명}’을 만들었습니다 (시험중).`);
    void loadMacros();
  };

  const promote = async (m: RpaMacro) => {
    const last = state?.runs.find((r) => r.매크로 === m.id && (r.모드 === '미리채움' || r.모드 === '학습'));
    const warn = !last ? '\n아직 미리 채워 보기 기록이 없습니다.' : last.사람 > 0 ? `\n최근 미리 채워 보기에서 사람 단계가 ${last.사람}개 남았습니다.` : '';
    if (!window.confirm(`‘${m.표시명}’을 사용으로 올려 [신청]에 쓸 수 있게 합니다.${warn}`)) return;
    if (await call('/api/macros/promote', { id: m.id }, '사용으로 올렸습니다.')) void loadMacros();
  };

  const setCompanyState = (b: RpaBusiness, 상태: CompanyState) => {
    const 사유 = 상태 === '불가' && !b.사유 ? window.prompt(`${b.사업장명} — 불가 사유 (예: 수납 미납 → 다음 신청)`, '') ?? '' : b.사유;
    void call('/api/companies', { items: [{ key: b.key, 상태, 사유 }] });
  };

  const saveReason = (b: RpaBusiness, 사유: string) =>
    void call('/api/companies', { items: [{ key: b.key, 사유 }] }, '사유를 저장했습니다.');

  const toggleCompany = (key: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  // 회차 체크 = 그 회차의 (보이는) 신청가능 업체 전체
  const toggleRound = (businesses: RpaBusiness[]) => {
    const keys = businesses.filter(selectable).map((b) => b.key);
    setPicked((prev) => {
      const next = new Set(prev);
      const all = keys.every((k) => next.has(k));
      keys.forEach((k) => (all ? next.delete(k) : next.add(k)));
      return next;
    });
  };

  // 보이는 순서대로 신청가능 업체 N곳 (회차 경계를 넘어 고른다)
  const pickFirst = (n: number) => {
    const keys = visible.flatMap((v) => v.businesses.filter(selectable).map((b) => b.key)).slice(0, n);
    setPicked(new Set(keys));
    onShowToast?.(`신청가능 업체 ${keys.length}곳을 골랐습니다.`, 'info');
  };

  const toggleDetail = (folder: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(folder)) next.delete(folder);
      else next.add(folder);
      return next;
    });

  const open = openKey ? byKey.get(openKey) : undefined;
  const kpi = state?.kpi ?? {};

  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" style={{ minHeight: compact ? '40vh' : '70vh' }}>
      {!compact && (
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-bold text-slate-900">HRD-Net 비용신청</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            순서: ① 통합 DATA 시트에서 「HRD-Net 비용신청 올리기」 → ② 증빙 폴더의 회차 &gt; 업체 폴더에 전자계산서·수납확인서 넣기(자동으로 신청가능) →
            ③ 업체를 체크하고 단계 실행 → ④ 「4 결과표」. 진행과 질문(사람이 눌러야 할 곳)은 오른쪽 패널에 뜹니다.
          </p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3 text-xs">
        <span className={`inline-flex items-center gap-1 ${state?.hrdnet.length ? 'text-emerald-700' : 'text-rose-600'}`}>
          ● {state?.hrdnet.length ? 'HRD-Net 창 있음' : 'HRD-Net 창 없음'}
        </span>
        <span className="text-slate-300">|</span>
        <span className={state?.busy ? 'text-amber-600' : 'text-emerald-700'}>
          ● {state?.busy ? `실행 중: ${state.label}` : '대기'}
        </span>
        {!offline && (
          <span className="text-slate-500">
            업체 {kpi.업체 ?? 0} · 신청가능 {kpi.업체_신청가능 ?? 0} · 증빙대기 회차 {kpi.증빙대기 ?? 0}
          </span>
        )}
        {offline && <span className="text-rose-600">엔진에 연결되지 않았습니다. 「사이드 패널 열기」를 먼저 누르세요.</span>}
        <div className="ml-auto flex flex-wrap gap-2">
          <button type="button" onClick={() => void openPanel()}
            className="rounded-lg border border-indigo-300 bg-white px-3 py-1 font-semibold text-indigo-700 hover:bg-indigo-50">
            사이드 패널 열기
          </button>
          <button type="button" onClick={() => void relayout()} disabled={offline}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            title="모니터 2개면 대시보드를 다른 모니터로, 1개면 한 화면에 3개 창을 나눠 놓습니다">
            창 다시 배치
          </button>
          {compact && (
            <button type="button" onClick={() => setCompact(false)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50">
              전체 보기
            </button>
          )}
          <button type="button" onClick={organize} disabled={offline || state?.busy}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40">
            ▶ 정리 {compact ? '' : '(대상 회차 묶기 · 업체 폴더 만들기)'}
          </button>
          <button type="button" onClick={() => void call('/api/open', { what: '증빙' })} disabled={offline}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40">
            증빙 폴더
          </button>
          {!compact && (
            <>
              <button type="button" onClick={() => void call('/api/open', { what: 'status' })} disabled={offline}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                title="자동 신청 중 건너뛴 업체와 확인 부탁할 내용(질문목록.md)이 있는 폴더">
                확인요청 목록
              </button>
              <button type="button" onClick={() => void backup(withTest)} disabled={offline || state?.busy}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                title="신청 성공한 회차의 파일을 지우지 않고 백업 폴더로 옮깁니다. 오른쪽 체크를 켜면 모의·점검·채움 회차도 포함합니다.">
                백업·정리
              </button>
              <label className="flex items-center gap-1 text-[11px] text-slate-600" title="연습(모의 실행 등)으로 끝난 회차도 백업으로 옮깁니다.">
                <input type="checkbox" checked={withTest} onChange={(e) => setWithTest(e.target.checked)} />
                모의·점검 회차도
              </label>
              <button type="button" onClick={makeResult} disabled={offline || state?.busy}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                title="오늘 실행한 기록을 결과표(엑셀)와 완료처리 대상(CSV)으로 만들고 폴더를 엽니다.">
                4 결과표
              </button>
              <button type="button" onClick={() => void run(['report'], '보낼 파일(zip)을 만들었습니다. 열린 logs 폴더의 「보낼파일_…zip」을 메일에 첨부해 주세요.')}
                disabled={offline || state?.busy}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                title="문제가 생기면: 최근 실행 기록·멈춘 화면·화면 진단을 zip 하나로 묶습니다.">
                보낼 파일 만들기
              </button>
            </>
          )}
          <button type="button" onClick={() => void window.rpaApi?.call({ method: 'POST', path: '/api/stop', body: {} })}
            className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-1 font-semibold text-rose-700 hover:bg-rose-100">
            ■ 멈춤
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-2 text-xs">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="업체명 · 관리번호 · 과정 · 회차 검색"
          className="w-56 rounded border border-slate-300 px-2 py-1" />
        <select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className="rounded border border-slate-300 px-2 py-1">
          {(['전체', ...COMPANY_STATES, '증빙대기'] as Filter[]).map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <span className="text-slate-300">|</span>
        {[50, 100].map((n) => (
          <button key={n} type="button" onClick={() => pickFirst(n)}
            className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-semibold text-slate-700 hover:bg-slate-100">
            {n}개 선택
          </button>
        ))}
        <button type="button" onClick={() => setPicked(new Set())}
          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-slate-600 hover:bg-slate-100">
          선택 해제
        </button>
        <button type="button" onClick={() => setExpanded(expanded.size ? new Set() : new Set(visible.map((v) => v.round.folder)))}
          className="rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-slate-600 hover:bg-slate-100">
          {expanded.size ? '모두 접기' : '모두 펼치기'}
        </button>
        <span className="ml-auto text-slate-500">{picked.size}개 업체 선택</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-5 py-3">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-white text-slate-500">
            <tr className="border-b border-slate-200">
              <th className="w-8 py-2" />
              <th className="py-2">과정</th>
              <th className="py-2">회차</th>
              <th className="py-2">업체</th>
              {!compact && <th className="py-2">신청가능 / 증빙대기 / 제외</th>}
              <th className="py-2">정리</th>
              <th className="py-2">올리기 결과</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-400">
                  {rounds.length === 0 ? '아직 정리된 회차가 없습니다. 위의 「▶ 정리」를 누르세요.' : '조건에 맞는 업체가 없습니다.'}
                </td>
              </tr>
            )}
            {visible.map(({ round: r, businesses }) => {
              const isExpanded = expanded.has(r.folder);
              const can = businesses.filter(selectable);
              const on = can.filter((b) => picked.has(b.key)).length;
              return (
                <React.Fragment key={r.folder}>
                  <tr className={`border-b border-slate-100 ${isExpanded ? 'bg-indigo-50/40' : ''}`}>
                    <td className="py-1.5">
                      <input type="checkbox" disabled={can.length === 0} checked={can.length > 0 && on === can.length}
                        ref={(el) => { if (el) el.indeterminate = on > 0 && on < can.length; }}
                        onChange={() => toggleRound(businesses)} title="이 회차의 신청가능 업체 전체" />
                    </td>
                    <td className="max-w-[18rem] truncate py-1.5" title={r.과정명}>{r.과정명}</td>
                    <td className="py-1.5">{r.회차}</td>
                    <td className="py-1.5">
                      <button type="button" onClick={() => toggleDetail(r.folder)}
                        className="rounded px-1.5 py-0.5 font-semibold text-indigo-700 hover:bg-indigo-100"
                        aria-expanded={isExpanded} title="업체 세부 내역 보기">
                        {isExpanded ? '▾' : '▸'} {businesses.length}{businesses.length !== r.사업장 ? `/${r.사업장}` : ''}곳
                        {on > 0 && <span className="ml-1 text-[10px] text-indigo-500">({on} 선택)</span>}
                      </button>
                    </td>
                    {!compact && (
                      <td className="py-1.5" title={Object.entries(r.제외 || {}).map(([why, n]) => `${why} ${n}곳`).join(', ') || '제외 없음 — 통합 DATA 시트와 업체 수가 같습니다'}>
                        <b className="text-emerald-700">{r.신청가능}</b> / <span className="text-amber-700">{r.증빙대기}</span>
                        {' / '}<span className="text-slate-500">{Object.values(r.제외 || {}).reduce((a: number, n: number) => a + n, 0)}</span>
                        {Object.keys(r.제외 || {}).length > 0 && (
                          <span className="ml-1 text-[10px] text-slate-400">({Object.entries(r.제외 || {}).map(([why, n]) => `${why} ${n}`).join(' · ')})</span>
                        )}
                      </td>
                    )}
                    <td className={`py-1.5 font-semibold ${r.정리 === '준비완료' ? 'text-emerald-700' : 'text-amber-600'}`}>{r.정리}</td>
                    <td className="py-1.5" title={r.오류}>{r.올리기}</td>
                  </tr>
                  {isExpanded && (
                    <tr className="border-b border-indigo-100 bg-indigo-50/30">
                      <td colSpan={7} className={compact ? 'px-2 py-2' : 'px-8 py-3'}>
                        <CompanyTable businesses={businesses} picked={picked} compact={compact} openKey={openKey}
                          onToggle={toggleCompany} onState={setCompanyState} onOpen={(b) => setOpenKey(b.key === openKey ? '' : b.key)} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        {rounds.some((r) => r.증빙대기 > 0) && !compact && (
          <p className="mt-2 text-[11px] text-amber-700">
            증빙 대기 업체는 「증빙 폴더」의 회차 &gt; 업체 폴더에 전자계산서·수납확인서 2개를 넣으면 몇 초 안에 신청가능으로 바뀝니다.
          </p>
        )}
      </div>

      {!compact && (
        <div className="border-t border-slate-200 px-5 py-3">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-bold text-slate-800">백업 보관함</span>
            <span className="text-slate-500">
              {backups ? `${backups.items.length}건 · 보관 ${backups.keep_days > 0 ? `${backups.keep_days}일` : '삭제 안 함'}` : ''}
              {backups?.archive_root ? ` · 장기 보관처: ${backups.archive_root}` : ' · 장기 보관처 미지정(local.json의 archive_root)'}
            </span>
            <button type="button" onClick={() => void window.rpa?.openBackup()}
              className="ml-auto rounded-lg border border-slate-300 bg-white px-2.5 py-1 font-semibold text-slate-700 hover:bg-slate-50">
              백업 폴더 열기
            </button>
          </div>
          {backups && backups.items.length === 0 && (
            <p className="text-[11px] text-slate-400">아직 백업이 없습니다. 위의 「백업·정리」를 누르면 끝난 회차가 여기에 쌓입니다.</p>
          )}
          <div className="max-h-56 space-y-2 overflow-auto">
            {backups?.items.map((b) => (
              <details key={b.name} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                <summary className="cursor-pointer select-none">
                  <span className="font-semibold text-slate-800">{b.시각}</span>
                  <span className="ml-2 text-slate-600">회차 {b.회차.length}개 · 파일 {b.파일}개 · {b.MB}MB</span>
                  <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-semibold ${b.장기보관 ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                    {b.장기보관 ? '장기 보관 완료' : '장기 보관 전'}
                  </span>
                  {b.삭제예정 && <span className="ml-2 text-slate-400">삭제 예정 {b.삭제예정}</span>}
                </summary>
                <ul className="mt-2 space-y-1">
                  {b.회차.map((r) => (
                    <li key={r.folder} className="flex flex-wrap gap-x-3 text-slate-700">
                      <span className="max-w-[26rem] truncate" title={r.folder}>{r.folder}</span>
                      <span>{r.사업장}곳</span>
                      <span className="font-semibold">{r.상태 || '-'}</span>
                      <span className="text-slate-400">{r.끝}</span>
                    </li>
                  ))}
                  <li className="pt-1 font-mono text-[10px] text-slate-400">{b.path}</li>
                </ul>
              </details>
            ))}
          </div>
        </div>
      )}

      <MacroBar macros={macros} runs={state?.runs ?? []} pickedCount={picked.size} roundCount={pickedRounds.length}
        disabled={offline || Boolean(state?.busy)} onSelect={(id) => void selectMacro(id)} onStart={start} onLearn={learn}
        onClone={() => void cloneMacro()} onPromote={(m) => void promote(m)} />

      <StatusDrawer business={open?.business ?? null} roundLabel={open ? `${open.round.과정명} ${open.round.회차}회차` : ''}
        slots={macros?.slots ?? {}} onClose={() => setOpenKey('')} onSaveReason={saveReason} />
    </div>
  );
};
