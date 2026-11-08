/** Графикуудын нийтлэг тэмдэглэгээ. */

export function minutesText(seconds) {
  const minutes = Math.round((seconds || 0) / 60);
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  return minutes % 60 ? `${hours} цаг ${minutes % 60} мин` : `${hours} цаг`;
}

export const SCORE_PARTS = [
  ['task_completion', 'T', 'Даалгаврын гүйцэтгэл', 0.4],
  ['quality', 'Q', 'Чанарын үнэлгээ', 0.3],
  ['deadline_completion', 'D', 'Хугацаандаа дуусгасан', 0.2],
  ['work_process', 'W', 'Ажлын програмын хувь', 0.1],
];
