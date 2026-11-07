function translate(message) {
  if (message === 'This password is too common.')
    return 'Энэ нууц үг хэт түгээмэл байна. Таахад хэцүү, өөр нууц үг сонгоно уу.';
  if (message === 'This password is entirely numeric.')
    return 'Нууц үг зөвхөн тооноос бүрдэж болохгүй. Үсэг нэмж оруулна уу.';
  if (message.startsWith('The password is too similar to '))
    return 'Нууц үг таны нэр эсвэл бүртгэлийн мэдээлэлтэй хэт төстэй байна. Өөр нууц үг сонгоно уу.';
  const short = message.match(/(?:at least|has at least) (\d+) characters/);
  if (short) return `Нууц үг хамгийн багадаа ${short[1]} тэмдэгттэй байна.`;
  const long = message.match(/at most (\d+) characters/);
  if (long) return `Нууц үг хамгийн ихдээ ${long[1]} тэмдэгттэй байна.`;
  if (message === 'This field may not be blank.') return 'Нууц үгээ оруулна уу.';
  return message;
}

export function passwordFeedback(failure) {
  for (const field of ['current_password', 'password', 'new_password', 'confirm_password']) {
    const value = failure.details?.[field];
    if (typeof value === 'string' || Array.isArray(value)) {
      const messages = Array.isArray(value) ? value : [value];
      return {field, message:messages.filter(item => typeof item === 'string').map(translate).join(' ')};
    }
  }
  return {field:null, message:failure.message};
}
