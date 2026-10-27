import type { SourceBundle } from "../../lib/api/g2-generated";

/** 文件读取开始时冻结目标草稿与修订；新建缓冲用null表示。 */
export type SourceImportTarget = { draftId: string | null; revision: number | null };

/** 单次读取票据；字段代次隔离同源并发，工作区代次隔离切换、丢弃与命令。 */
export type SourceImportTicket = SourceImportTarget & { field: keyof SourceBundle; epoch: number; generation: number };

/** 编辑器只提交仍有效的文件读取，不持有整份旧草稿。 */
export type SourceImportHandle = { isCurrent: () => boolean; commit: (value: string) => void };

/** 本地文件读取的失效边界，不发送请求，也不解析或重建RDF。 */
export class SourceImportSession {
  private epoch = 0;
  private generations: Record<keyof SourceBundle, number> = {
    ontologyTurtle: 0, shapesTurtle: 0, vocabularyTurtle: 0, dataTurtle: 0,
  };

  /** 同源新导入立即使旧读取失效，包含之后因大小或UTF8失败的导入。 */
  begin(field: keyof SourceBundle, target: SourceImportTarget): SourceImportTicket {
    this.invalidate(field);
    return { ...target, field, epoch: this.epoch, generation: this.generations[field] };
  }

  /** 同源键入只取消该源；工作区边界取消全部未完成读取。 */
  invalidate(field?: keyof SourceBundle) {
    if (field) this.generations[field] += 1;
    else this.epoch += 1;
  }

  /** 过期票据永不重新有效，完成顺序不决定获胜者。 */
  isCurrent(ticket: SourceImportTicket): boolean {
    return ticket.epoch === this.epoch && ticket.generation === this.generations[ticket.field];
  }
}
