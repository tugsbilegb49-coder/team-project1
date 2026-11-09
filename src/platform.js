/** Browser болон WorkTrack launcher нэг компьютер дээр ажилладаг тул browser-ийн системээр шийднэ. */
export const isWindows = typeof navigator !== 'undefined' && /Windows/i.test(navigator.userAgent);

/** WorkTrack-ийг дахин асаахдаа нээх файл. */
export const launcherName = isWindows ? 'Start WorkTrack.bat' : 'WorkTrack.app';

/** Тухайн системийн launcher-ийн бүх хувилбар (macOS дээр .app болон .command хоёулаа ажиллана). */
export const launcherChoices = isWindows
  ? 'Start WorkTrack.bat'
  : 'WorkTrack.app эсвэл Start WorkTrack.command';
