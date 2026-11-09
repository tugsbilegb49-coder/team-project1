import { useEffect, useRef, useState } from 'react';
import { passwordFeedback } from './passwordFeedback';
import { MemberResetCode } from './ResetPassword';

const ROLE_NAMES = { EMPLOYEE: 'Ажилтан', MANAGER: 'Менежер', ADMIN: 'Админ' };

function MemberPasswordReset({ member, busy, mutate }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const button = useRef(null),
    input = useRef(null),
    confirmation = useRef(null),
    errorNote = useRef(null);
  const formId = `reset-password-${member.id}`;

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  useEffect(() => {
    if (error && !busy) {
      if (error.field === 'password') input.current?.focus();
      if (error.field === 'confirm_password') confirmation.current?.focus();
      errorNote.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [error, busy]);

  function close() {
    setOpen(false);
    setError(null);
    button.current?.focus();
  }

  async function save(event) {
    event.preventDefault();
    if (busy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setError(null);
    if (data.get('password') !== data.get('confirm_password')) {
      setError({ field: 'confirm_password', message: 'Шинэ нууц үгүүд ижил байх ёстой.' });
      return;
    }
    if (
      await mutate(
        `/api/users/${member.id}/`,
        'PATCH',
        { password: data.get('password') },
        { onError: (failure) => setError(passwordFeedback(failure)) },
      )
    ) {
      form.reset();
      close();
      setSaved(true);
    }
  }

  return (
    <div className="member-password">
      <button
        ref={button}
        type="button"
        disabled={busy}
        aria-expanded={open}
        aria-controls={formId}
        onClick={() => {
          if (open) close();
          else {
            setSaved(false);
            setOpen(true);
          }
        }}
      >
        Нууц үг шинэчлэх
      </button>
      {open && (
        <form
          id={formId}
          className="task-form"
          aria-label={`Нууц үг шинэчлэх — ${member.username}`}
          onSubmit={save}
        >
          <p>
            <strong>{member.username}</strong> хэрэглэгчийн нууц үгийг шинэчилнэ. Ажилтан дахин
            нэвтэрч, төхөөрөмжөө дахин холбоно.
          </p>
          <fieldset disabled={busy}>
            <label htmlFor={`${formId}-new`}>Шинэ нууц үг</label>
            <input
              ref={input}
              id={`${formId}-new`}
              name="password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={256}
              required
              aria-invalid={error?.field === 'password'}
              aria-describedby={error?.field === 'password' ? `${formId}-error` : undefined}
              onChange={() => setError(null)}
            />
            {error?.field === 'password' && (
              <p ref={errorNote} id={`${formId}-error`} className="field-error" role="alert">
                {error.message}
              </p>
            )}
            <label htmlFor={`${formId}-confirm`}>Шинэ нууц үг давтах</label>
            <input
              ref={confirmation}
              id={`${formId}-confirm`}
              name="confirm_password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={256}
              required
              aria-invalid={error?.field === 'confirm_password'}
              aria-describedby={error && error.field !== 'password' ? `${formId}-error` : undefined}
              onChange={() => setError(null)}
            />
            {error && error.field !== 'password' && (
              <p ref={errorNote} id={`${formId}-error`} className="field-error" role="alert">
                {error.message}
              </p>
            )}
            <div className="desktop-actions">
              <button type="submit">{busy ? 'Хадгалж байна…' : 'Шинэ нууц үг хадгалах'}</button>
              <button type="button" onClick={close}>
                Болих
              </button>
            </div>
          </fieldset>
        </form>
      )}
      {saved && (
        <p role="status">
          Нууц үг шинэчлэгдлээ. Ажилтанд шинэ нууц үгийг хувийн сувгаар өгнө үү. Нэвтэрсний дараа
          “Миний бүртгэл” хэсэгт өөрийн нууц үгээр сольж болно.
        </p>
      )}
    </div>
  );
}

export default function Members({ user, members, departments, busy, mutate }) {
  const [role, setRole] = useState('EMPLOYEE');
  const [department, setDepartment] = useState('');
  const [editingId, setEditingId] = useState(null);
  return (
    <section>
      <h1>Багийн гишүүд</h1>
      {user.is_admin && (
        <>
          <form
            className="task-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const name = new FormData(form).get('name').trim();
              if (name && (await mutate('/api/departments/', 'POST', { name }))) form.reset();
            }}
          >
            <h2>Хэлтэс нэмэх</h2>
            <fieldset disabled={busy}>
              <label htmlFor="department-name">Хэлтсийн нэр</label>
              <input id="department-name" name="name" required maxLength={120} />
              <button type="submit">Хэлтэс нэмэх</button>
            </fieldset>
          </form>
          {departments.length > 0 && (
            <section className="department-edit-list" aria-label="Хэлтэс засах">
              <h2>Хэлтсийн жагсаалт</h2>
              {departments.map((row) => (
                <form
                  className="department-edit-row"
                  key={row.id}
                  onSubmit={async (event) => {
                    event.preventDefault();
                    const name = new FormData(event.currentTarget).get('name').trim();
                    if (name) await mutate(`/api/departments/${row.id}/`, 'PATCH', { name });
                  }}
                >
                  <fieldset disabled={busy}>
                    <label htmlFor={`department-edit-${row.id}`}>«{row.name}» хэлтсийн нэр</label>
                    <input
                      id={`department-edit-${row.id}`}
                      name="name"
                      defaultValue={row.name}
                      required
                      maxLength={120}
                    />
                  </fieldset>
                  <button type="submit" disabled={busy}>
                    Нэр хадгалах
                  </button>
                  <button
                    type="button"
                    className="delete-button"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm(
                          `"${row.name}" хэлтсийг устгах уу? Ажилтнууд хэлтэсгүй болно.`,
                        )
                      )
                        mutate(`/api/departments/${row.id}/`, 'DELETE');
                    }}
                  >
                    Хэлтэс устгах
                  </button>
                </form>
              ))}
            </section>
          )}
          <form
            className="task-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const data = Object.fromEntries(new FormData(form));
              data.department = department ? Number(department) : null;
              if (await mutate('/api/users/', 'POST', data)) {
                form.reset();
                setRole('EMPLOYEE');
                setDepartment('');
              }
            }}
          >
            <h2>Гишүүн нэмэх</h2>
            <fieldset disabled={busy}>
              <label htmlFor="member-username">Хэрэглэгчийн нэр</label>
              <input id="member-username" name="username" required autoComplete="off" />
              <label htmlFor="member-name">Нэр</label>
              <input id="member-name" name="first_name" required />
              <label htmlFor="member-email">Имэйл</label>
              <input id="member-email" name="email" type="email" />
              <label htmlFor="member-password">Анхны нууц үг</label>
              <input
                id="member-password"
                name="password"
                type="password"
                minLength={8}
                autoComplete="new-password"
                required
              />
              <label htmlFor="member-role">Эрх</label>
              <select
                id="member-role"
                name="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <option value="EMPLOYEE">Ажилтан</option>
                <option value="MANAGER">Менежер</option>
                <option value="ADMIN">Админ</option>
              </select>
              <label htmlFor="member-department">
                Хэлтэс{role === 'MANAGER' ? ' (заавал)' : ''}
              </label>
              <select
                id="member-department"
                value={department}
                onChange={(event) => setDepartment(event.target.value)}
                required={role === 'MANAGER'}
              >
                <option value="">Хэлтэс сонгох</option>
                {departments.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </select>
              {role === 'MANAGER' && !departments.length && (
                <p>Менежер нэмэхийн өмнө хэлтэс үүсгэнэ үү.</p>
              )}
              <button type="submit" disabled={role === 'MANAGER' && !departments.length}>
                Гишүүн нэмэх
              </button>
            </fieldset>
          </form>
        </>
      )}
      {members.map((member) => (
        <article className="task-item member-item" key={member.id}>
          <div className="member-details">
            <h3>{member.name}</h3>
            <p>
              Нэвтрэх нэр: <strong>{member.username}</strong>
            </p>
            <p>
              {[
                member.email,
                ROLE_NAMES[member.role] || member.role,
                !member.is_active && 'Идэвхгүй',
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
            {user.is_admin ? (
              <label>
                Хэлтэс — {member.name}
                <select
                  aria-label={`Хэлтэс — ${member.name}`}
                  value={member.department ?? ''}
                  disabled={busy}
                  onChange={(event) =>
                    mutate(`/api/users/${member.id}/`, 'PATCH', {
                      department: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                >
                  <option value="" disabled={member.role === 'MANAGER'}>
                    Хэлтэсгүй
                  </option>
                  {departments.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <small>{member.department_name || 'Хэлтэсгүй'}</small>
            )}
            {user.is_admin && member.id !== user.id && member.is_active && (
              <>
                <MemberResetCode member={member} busy={busy} />
                <MemberPasswordReset member={member} busy={busy} mutate={mutate} />
              </>
            )}
            {user.is_admin && member.id !== user.id && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setEditingId(editingId === member.id ? null : member.id)}
              >
                {editingId === member.id ? 'Засвар хаах' : 'Мэдээлэл засах'}
              </button>
            )}
          </div>
          {user.is_admin && member.id !== user.id && (
            <div className="member-actions">
              {member.is_active && (
                <button
                  disabled={busy}
                  onClick={() => mutate(`/api/users/${member.id}/`, 'PATCH', { is_active: false })}
                >
                  Идэвхгүй болгох
                </button>
              )}
              <button
                className="delete-button"
                disabled={busy}
                onClick={() => {
                  const confirmed = window.confirm(
                    `"${member.name}" хэрэглэгч болон түүнд холбогдсон бүртгэлүүдийг бүрмөсөн устгах уу?`,
                  );
                  if (confirmed) mutate(`/api/users/${member.id}/`, 'DELETE');
                }}
              >
                Бүрмөсөн устгах
              </button>
            </div>
          )}
          {user.is_admin && editingId === member.id && (
            <form
              className="member-edit-form"
              onSubmit={async (event) => {
                event.preventDefault();
                const data = Object.fromEntries(new FormData(event.currentTarget));
                data.department = data.department ? Number(data.department) : null;
                data.is_active = data.is_active === 'on';
                if (await mutate(`/api/users/${member.id}/`, 'PATCH', data)) setEditingId(null);
              }}
            >
              <label>
                Нэр
                <input name="first_name" defaultValue={member.first_name} required />
              </label>
              <label>
                Овог
                <input name="last_name" defaultValue={member.last_name} />
              </label>
              <label>
                Имэйл
                <input name="email" type="email" defaultValue={member.email} />
              </label>
              <label>
                Эрх
                <select name="role" defaultValue={member.role}>
                  <option value="EMPLOYEE">Ажилтан</option>
                  <option value="MANAGER">Менежер</option>
                  <option value="ADMIN">Админ</option>
                </select>
              </label>
              <label>
                Хэлтэс
                <select name="department" defaultValue={member.department ?? ''}>
                  <option value="">Хэлтэсгүй</option>
                  {departments.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="member-active-toggle">
                <input type="checkbox" name="is_active" defaultChecked={member.is_active} />{' '}
                Идэвхтэй
              </label>
              <button type="submit" disabled={busy}>
                Өөрчлөлт хадгалах
              </button>
            </form>
          )}
        </article>
      ))}
    </section>
  );
}
