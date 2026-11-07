import { useEffect, useRef, useState } from 'react';
import { api, clearAuth, desktop } from './api';
import { LauncherClock } from './WorkClocks';

function duration(seconds) {
  if(Number(seconds || 0)<60)return `${Math.floor(Number(seconds || 0))} сек`;
  const minutes=Math.floor(Number(seconds || 0)/60);
  return `${Math.floor(minutes/60)} цаг ${minutes%60} мин`;
}

export function DesktopPanel({user}) {
  const [state,setState]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [step,setStep]=useState(1),[deviceName,setDeviceName]=useState('Миний компьютер'),[consent,setConsent]=useState(false);
  const [relink,setRelink]=useState(false),[closed,setClosed]=useState(false),[reload,setReload]=useState(0);
  const actionController=useRef(null),running=useRef(false),latest=useRef(0);
  useEffect(()=>{
    const controller=new AbortController();const flight={busy:false};
    async function poll(){
      if(flight.busy || running.current || closed)return;
      flight.busy=true;const request=++latest.current;
      try{const data=await desktop('status',{signal:controller.signal});
        if(!controller.signal.aborted && latest.current===request){setState(data);setError('');}}
      catch(failure){if(!controller.signal.aborted && failure.name!=='AbortError' && latest.current===request)setError(failure.message);}
      finally{flight.busy=false;}
    }
    poll();const timer=setInterval(poll,5000);
    return()=>{controller.abort();clearInterval(timer);};
  },[user.id,reload,closed]);
  useEffect(()=>()=>{actionController.current?.abort();},[]);
  async function act(action,body={}) {
    if(running.current)return;
    running.current=true;++latest.current;setBusy(true);setError('');
    const controller=new AbortController();actionController.current=controller;
    try{
      const data=await desktop(action,{method:'POST',body:JSON.stringify(body),signal:controller.signal});
      if(!controller.signal.aborted){setState(data);if(action==='connect')setRelink(false);if(action==='quit')setClosed(true);}
    }catch(failure){if(!controller.signal.aborted && failure.name!=='AbortError')setError(failure.message);}
    finally{running.current=false;if(!controller.signal.aborted)setBusy(false);}
  }
  const runningWork=state?.computer_running;
  return <section className="desktop-panel" aria-label="Энэ компьютерийн удирдлага">
    <h2>Миний төхөөрөмж</h2>
    {closed ? <p role="status">WorkTrack хаагдаж байна. Дараа WorkTrack.app-аа нээгээрэй.</p> : <>
      {error && <p role="alert">{error}</p>}
      {!state && !error && <p>Төхөөрөмжтэй холбогдож байна…</p>}
      {!state && error && <button onClick={()=>setReload(v=>v+1)}>Дахин холбогдох</button>}
      {state && <>
        <p>{state.linked ? `${state.device_name} · ${state.username}`:'Энэ компьютерт account-аа холбоно уу.'}</p>
        {state.another_account ? <p>Өөр account-ийн ажил үргэлжилж байна. Тэр account-аар нэвтэрч ажлаа дуусгана уу.</p> : (!state.linked || relink) ?
          <form onSubmit={event=>{event.preventDefault();if(step<3)setStep(step+1);else act('connect',{device_name:deviceName,consent});}}>
            <fieldset disabled={busy}><legend>Анхны тохиргоо · {step}/3</legend>
              {step===1 && <><p>1. Энэ төхөөрөмж {user.username} account-д хугацаа бүртгэнэ.</p>
                <label>Төхөөрөмжийн нэр<input required maxLength={120} value={deviceName} onChange={e=>setDeviceName(e.target.value)}/></label></>}
              {step===2 && <><p>2. Идэвхтэй аппын нэр, ашигласан хугацаа, idle хугацааг бүртгэнэ. Бичсэн текст, URL, screenshot хадгалахгүй.</p>
                <p>Account-тай холбосны дараа WorkTrack нээлттэй байсан хугацаа мөн сарын тайланд админд харагдана.
                  Ажил түр зогсоосон үед ч програмын нээлттэй цаг тоологдоно; бүрэн зогсоох бол WorkTrack-аа хаах эсвэл төхөөрөмжөө салгана.</p>
                <p>Camera тусдаа товчоор асна. Зураг, видео хадгалахгүй; зөвхөн presence/confidence бүртгэнэ.</p>
                <label className="toggle-field"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Мэдээлэл бүртгэхийг зөвшөөрч байна (2026-11)</label></>}
              {step===3 && <p>3. {deviceName} төхөөрөмжийг {user.username}-тай холбоно. Дараа нь “Ажил эхлүүлэх” дарна; camera автоматаар асахгүй.</p>}
              <div className="desktop-actions">
                {step>1 && <button type="button" onClick={()=>setStep(step-1)}>Буцах</button>}
                <button type="submit" disabled={step===2 && !consent}>{busy?'Холбож байна…':step===3?'Төхөөрөмж холбох':'Үргэлжлүүлэх'}</button>
                {relink && <button type="button" onClick={()=>setRelink(false)}>Болих</button>}
              </div>
            </fieldset>
          </form> : <>
            <p role="status">{runningWork ? state.paused?'Ажил түр зогссон':'Ажил бүртгэж байна':'Ажил эхлээгүй'} · Camera {state.camera_running ? state.paused?'түр зогссон':'асаалттай':'унтраалттай'}</p>
            <div className="desktop-actions">
              {!runningWork ? <button disabled={busy} onClick={()=>act('start')}>Ажил эхлүүлэх</button> :
                <button disabled={busy} onClick={()=>act(state.paused?'resume':'pause')}>{state.paused?'Ажил үргэлжлүүлэх':'Түр зогсоох'}</button>}
              <button disabled={busy || (!runningWork && !state.camera_running)} onClick={()=>act('stop')}>Ажил дуусгах</button>
              <button disabled={busy || (!state.camera_running && (!runningWork || state.paused || !state.camera_ready || state.preparing_camera))}
                onClick={()=>act(state.camera_running?'camera-off':'camera-on')}>{state.camera_running?'Camera унтраах':'Camera асаах'}</button>
              <button disabled={busy || state.camera_running || state.preparing_camera} onClick={()=>act('prepare-camera')}>
                {state.preparing_camera?'Camera бэлтгэж байна…':state.camera_ready?'Camera dependency шинэчлэх':'Camera бэлтгэх'}</button>
            </div>
            {state.errors?.length>0 && <p role="alert">{state.camera_error==='permission'
              ? 'Camera зөвшөөрөгдөөгүй. System Settings → Privacy & Security → Camera → WorkTrack Camera-ийг зөвшөөрөөд дахин асаана уу.'
              : state.camera_error==='setup' ? 'Camera launcher бэлтгэгдсэнгүй. Camera бэлтгэх товчийг дарж, Command Line Tools болон Python суулгалтаа шалгана уу.'
              : state.camera_error==='startup' ? 'Camera апп эхэлсэнгүй. macOS-ийн зөвшөөрлийн цонхыг шалгаад дахин асаана уу.'
              : `${state.errors.includes('agent')?'Agent':'Camera'} зогссон байна. Зөвшөөрөл/нэвтрэлтээ шалгаад дахин холбоно уу.`}</p>}
            {state.camera_setup_error && <p role="alert">Camera бэлтгэл амжилтгүй. Холболтоо шалгаад дахин бэлтгэнэ үү.</p>}
            <p className="muted">Вебээс гарахад бүртгэл үргэлжилнэ. Зогсоохдоо “Ажил дуусгах” дарна.</p>
            <details><summary>Төхөөрөмжийн нэмэлт үйлдэл</summary><div className="desktop-actions">
              <button disabled={busy || runningWork || state.camera_running} onClick={()=>{setStep(1);setConsent(false);setRelink(true);}}>Дахин холбох</button>
              <button disabled={busy} onClick={()=>act('disconnect')}>Холболт салгах</button>
              <button disabled={busy} onClick={()=>{if(window.confirm('Agent, camera болон WorkTrack-ийг хаах уу?'))act('quit');}}>WorkTrack хаах</button>
            </div></details>
          </>}
      </>}
    </>}
  </section>;
}

export default function Today({user,navigate}) {
  const [result,setResult]=useState(null),[error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();const flight={busy:false};
    async function load(){
      if(flight.busy)return;flight.busy=true;
      try{const data=await api('/api/me/today/',{signal:controller.signal});if(!controller.signal.aborted){setResult(data);setError('');}}
      catch(failure){if(!controller.signal.aborted && failure.name!=='AbortError')setError(failure.message);}
      finally{flight.busy=false;}
    }
    load();const timer=setInterval(load,30000);return()=>{controller.abort();clearInterval(timer);};
  },[user.id]);
  return <section className="today-page"><header className="header"><div><h1>Миний өнөөдөр</h1><p>{user.username} · {result?.date || 'Өнөөдрийн мэдээлэл'}</p></div></header>
    <section className="stats today-time-stats" aria-label="Хугацааны тойм">
      <LauncherClock user={user} card/>
      <article className="stat-card" aria-label="Өнөөдөр бүртгэгдсэн хугацаа">
        <p>Өнөөдөр бүртгэгдсэн хугацаа</p><h2>{result ? duration(result.tracked_seconds) : '—'}</h2>
        <small>Өнөөдрийн апп ашигласан болон идэвхгүй байсан (idle) хугацааны серверт хадгалагдсан нийлбэр.
          30 секунд тутам шинэчлэгдэнэ.</small>
      </article>
    </section>
    <DesktopPanel key={user.id} user={user}/>
    {error && <p role="alert">{error}</p>}
    {!result && !error && <p>Өнөөдрийн мэдээлэл уншиж байна…</p>}
    {result && <>
      <section className="stats today-task-stats"><article className="stat-card"><p>Дуусаагүй даалгавар</p><h2>{result.open_tasks}</h2></article>
        <article className="stat-card"><p>Хугацаа хэтэрсэн</p><h2>{result.overdue_tasks}</h2></article></section>
      <section className="activity-detail-card"><h2>Өнөөдөр ашигласан аппууд</h2>
        <p>Сүүлд бүртгэгдсэн апп: {result.latest_application?.application || 'Одоогоор бүртгэлгүй'}</p>
        {result.applications.map(row=><div className="activity-row" key={row.application}><span>{row.application}</span><strong>{duration(row.seconds)}</strong></div>)}
      </section>
      <section className="activity-detail-card"><h2>Миний хийх ажлууд</h2>
        {!result.tasks.length && <p>Дуусаагүй даалгавар алга.</p>}
        {result.tasks.map(task=><div className="activity-row" key={task.id}><span>{task.title}</span><strong>{task.due_date || 'Хугацаа заагаагүй'}</strong></div>)}
        <button onClick={()=>navigate('tasks')}>Даалгавраа харах</button>
      </section>
    </>}
  </section>;
}

export function PasswordSettings() {
  const [error,setError]=useState(''),[busy,setBusy]=useState(false);
  const controller=useRef(null);
  useEffect(()=>()=>controller.current?.abort(),[]);
  async function save(event){
    event.preventDefault();if(busy)return;
    const data=Object.fromEntries(new FormData(event.currentTarget));
    if(data.new_password!==data.confirm_password){setError('Шинэ нууц үгүүд ижил байх ёстой.');return;}
    setBusy(true);setError('');controller.current=new AbortController();const signal=controller.current.signal;
    try{
      await api('/api/me/password/',{method:'POST',body:JSON.stringify(data),signal});
      if(!signal.aborted)clearAuth('password_changed');
    }catch(failure){if(!signal.aborted && failure.name!=='AbortError')setError(failure.message);}
    finally{if(!signal.aborted)setBusy(false);}
  }
  return <section><h1>Миний бүртгэл</h1><form className="task-form" onSubmit={save}>
    <h2>Нууц үг солих</h2><p>Нууц үг солигдоход бүх session хүчингүй болно. Шинээр нэвтрээд төхөөрөмжөө дахин холбоно уу.</p>
    <fieldset disabled={busy}>
      <label>Одоогийн нууц үг<input required type="password" name="current_password" autoComplete="current-password" maxLength={256}/></label>
      <label>Шинэ нууц үг<input required type="password" name="new_password" autoComplete="new-password" minLength={8} maxLength={256}/></label>
      <label>Шинэ нууц үг давтах<input required type="password" name="confirm_password" autoComplete="new-password" minLength={8} maxLength={256}/></label>
      {error && <p role="alert">{error}</p>}<button type="submit">{busy?'Сольж байна…':'Нууц үг солих'}</button>
    </fieldset>
  </form></section>;
}
