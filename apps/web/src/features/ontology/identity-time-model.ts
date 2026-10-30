import type {
  ResourceScope, RdfTerm, VocabularyChange, VocabularyEditSource, VocabularySnapshot, VocabularySourceTriple,
} from "../../lib/api/g2-generated";
import { rdfType } from "./structural-edit";
import { semantic, xsd, vocabularyChange } from "./vocabulary-model";

export const time = "http://www.w3.org/2006/time#";
export const identityTypes = [
  { iri: semantic + "IdentityClaim", label: "身份声明" },
  { iri: time + "Instant", label: "时间点" },
  { iri: time + "Interval", label: "半开区间" },
  { iri: semantic + "Event", label: "事件" },
];
export const identityFields: Record<string, string> = Object.fromEntries([
  ...[["organizationId", "组织"], ["siteId", "厂区"], ["sourceNamespace", "来源命名空间"],
    ["externalIdentifier", "外部编号"], ["targetIri", "目标IRI"], ["declarationSource", "声明来源"],
    ["validityInterval", "业务有效区间"], ["observedAtUtc", "观察时间"]].map(([key, label]) => [semantic + key, label]),
  ...[["hasBeginning", "起点（含）"], ["hasEnd", "终点（不含）"], ["inXSDDateTimeStamp", "明确时区时间戳"],
    ["hasTime", "事件发生时间"]].map(([key, label]) => [time + key, label]),
]);
const named = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const literal = (value: string, datatype: string | null = null): RdfTerm => ({ kind: "literal", value, datatype, language: null });
export const absoluteIri = (value: string) => /^[A-Za-z][A-Za-z0-9+.-]*:[^<>"{}|^`\\\s]+$/.test(value);

/** 严格受控词法保留原时区与七位小数；不依赖本机时区或Date的日期自动进位。 */
export function timestampTicks(text: string): bigint | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,7}))?(Z|([+-])(\d{2}):(\d{2}))$/.exec(text);
  if (!match || match[0] !== text) return null;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, fraction = "", zone, sign, zoneHour, zoneMinute] = match;
  const year = Number(yearText), month = Number(monthText), day = Number(dayText);
  const hour = Number(hourText), minute = Number(minuteText), second = Number(secondText);
  const offsetHour = Number(zoneHour ?? 0), offsetMinute = Number(zoneMinute ?? 0);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1]
    || hour > 23 || minute > 59 || second > 59 || offsetHour > 14 || offsetMinute > 59
    || offsetHour === 14 && offsetMinute !== 0) return null;
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, 0);
  const offset = zone === "Z" ? 0 : (offsetHour * 60 + offsetMinute) * (sign === "+" ? 1 : -1);
  const utcMilliseconds = date.getTime() - offset * 60000;
  if (utcMilliseconds < -62135596800000 || utcMilliseconds > 253402300799999) return null;
  return BigInt(utcMilliseconds) * 10000n + BigInt(fraction.padEnd(7, "0"));
}

/** 多个同号声明按自身IRI逐项保留，不以标签或编号合并。 */
export function identityDirectory(snapshot: VocabularySnapshot, search = "") {
  const query = search.trim().toLocaleLowerCase();
  const iris = new Set(snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.predicate === rdfType
    && row.triple.object.kind === "iri" && identityTypes.some(type => type.iri === row.triple.object.value))
    .map(row => row.triple.subject.value));
  return [...iris].map(iri => ({ iri, rows: snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.subject.value === iri) }))
    .filter(item => !query || [item.iri, ...item.rows.map(row => row.triple.object.value)].some(value => value.toLocaleLowerCase().includes(query)))
    .sort((left, right) => left.iri.localeCompare(right.iri));
}

/** 表单所需单值必须真实、唯一，无法确定时拒绝而不挑第一个值。 */
function only(snapshot: VocabularySnapshot, iri: string, predicate: string, optional = false): VocabularySourceTriple | null {
  const rows = snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.subject.value === iri && row.triple.predicate === predicate);
  if (rows.length === 0 && optional) return null;
  if (rows.length !== 1) throw new Error("现有字段来源缺失或多值歧义，请查看真实诊断并使用源码修正。");
  return rows[0];
}
function fresh(snapshot: VocabularySnapshot, iris: string[]) {
  if (new Set(iris).size !== iris.length || iris.some(iri => !absoluteIri(iri))) throw new Error("每个资源必须有独立的绝对IRI。");
  if (snapshot.triples.some(row => row.triple.subject.kind === "iri" && iris.includes(row.triple.subject.value)))
    throw new Error("新资源IRI已被声明。请使用新的IRI，保留历史声明与时间事实。");
}
function add(sourceId: VocabularyEditSource, subjectIri: string, predicateIri: string, newObject: RdfTerm): VocabularyChange {
  return { sourceId, edit: { subjectIri, predicateIri, oldObject: null, newObject } };
}
function requireInterval(from: string, to: string) {
  const start = from ? timestampTicks(from) : null, end = to ? timestampTicks(to) : null;
  if (from && start === null || to && end === null) throw new Error("时间必须是明确Z或±hh:mm时区的有效日期时间，最多7位小数；空值保持未知。");
  if (start !== null && end !== null && start >= end) throw new Error("半开区间必须满足起点早于终点；终点不包含在有效期内。");
}
function temporalChanges(source: VocabularyEditSource, iri: string, kind: "point" | "interval", from: string, to: string) {
  requireInterval(kind === "point" ? "" : from, to);
  if (kind === "point" && from && timestampTicks(from) === null) throw new Error("时间点必须带明确时区，不能采用本机时区。");
  const changes = [add(source, iri, rdfType, named(time + (kind === "point" ? "Instant" : "Interval")))];
  if (kind === "point") {
    if (from) changes.push(add(source, iri, time + "inXSDDateTimeStamp", literal(from, xsd + "dateTimeStamp")));
  } else {
    for (const [endpoint, value] of [["from", from], ["to", to]]) {
      if (!value) continue;
      const point = `${iri}/${endpoint}`;
      changes.push(add(source, iri, time + (endpoint === "from" ? "hasBeginning" : "hasEnd"), named(point)),
        add(source, point, rdfType, named(time + "Instant")),
        add(source, point, time + "inXSDDateTimeStamp", literal(value, xsd + "dateTimeStamp")));
    }
  }
  return changes;
}
/** 新身份表单仅提供显式范围内编号、目标、来源和业务有效时间。 */
export interface ClaimInput {
  iri: string; siteId: string; sourceNamespace: string; externalIdentifier: string;
  targetIri: string; declarationSource: string; from: string; to: string;
}

/** 组织/厂区取草稿权威范围，新增命名声明与时间模板同批原子提交。 */
export function claimChanges(snapshot: VocabularySnapshot, scope: ResourceScope, source: VocabularyEditSource, input: ClaimInput): VocabularyChange[] {
  const { iri, targetIri, declarationSource, siteId, sourceNamespace, externalIdentifier, from, to } = input;
  if (!scope.siteIds.includes(siteId) || !scope.organizationId) throw new Error("身份组织和厂区必须属于当前资产范围。");
  if (!sourceNamespace.trim() || !externalIdentifier.trim()) throw new Error("来源命名空间与外部编号必须明确填写。");
  if (![iri, targetIri, declarationSource].every(absoluteIri)) throw new Error("声明、目标和来源必须是绝对IRI。");
  if (!snapshot.triples.some(row => row.triple.subject.kind === "iri" && row.triple.subject.value === targetIri
    && row.triple.predicate === rdfType && row.triple.object.kind === "iri")) throw new Error("目标IRI尚未在当前四源显式登记类型。");
  const interval = `${iri}/validity`;
  fresh(snapshot, [iri, interval, ...(from ? [interval + "/from"] : []), ...(to ? [interval + "/to"] : [])]);
  return [add(source, iri, rdfType, named(semantic + "IdentityClaim")),
    ...[["organizationId", scope.organizationId], ["siteId", siteId], ["sourceNamespace", sourceNamespace],
      ["externalIdentifier", externalIdentifier]].map(([key, value]) => add(source, iri, semantic + key, literal(value))),
    add(source, iri, semantic + "targetIri", named(targetIri)), add(source, iri, semantic + "declarationSource", named(declarationSource)),
    add(source, iri, semantic + "validityInterval", named(interval)), ...temporalChanges(source, interval, "interval", from, to)];
}

/** 关闭历史只增补或收窄原区间终点，绝不改编号、目标、来源或开始时间。 */
export function closeClaimChanges(snapshot: VocabularySnapshot, claimIri: string, until: string): VocabularyChange[] {
  if (!until || timestampTicks(until) === null) throw new Error("关闭有效期需要明确时区的已知终点。");
  const claim = only(snapshot, claimIri, semantic + "validityInterval")!;
  if (claim.triple.object.kind !== "iri") throw new Error("历史有效区间引用不是命名IRI。");
  const interval = claim.triple.object.value;
  const references = snapshot.triples.filter(row => row.triple.object.kind === "iri" && row.triple.object.value === interval);
  if (references.length !== 1) throw new Error("有效区间被多个资源共享；禁止在表单中隐式改变其它历史声明。");
  const from = only(snapshot, interval, time + "hasBeginning", true);
  if (from) {
    if (from.triple.object.kind !== "iri") throw new Error("历史起点不是命名IRI。");
    const stamp = only(snapshot, from.triple.object.value, time + "inXSDDateTimeStamp", true);
    requireInterval(stamp?.triple.object.value ?? "", until);
  }
  const end = only(snapshot, interval, time + "hasEnd", true);
  if (end) {
    if (end.triple.object.kind !== "iri") throw new Error("历史终点不是命名IRI。");
    if (snapshot.triples.filter(row => row.triple.object.kind === "iri" && row.triple.object.value === end.triple.object.value).length !== 1)
      throw new Error("历史终点被共享；请保留原事实并在源码检查引用。");
    const stamp = only(snapshot, end.triple.object.value, time + "inXSDDateTimeStamp", true);
    if (stamp && (timestampTicks(stamp.triple.object.value) === null || timestampTicks(until)! > timestampTicks(stamp.triple.object.value)!))
      throw new Error("历史有效期只能收窄，不能扩张或替换不确定的旧终点。");
    const change = stamp ? vocabularyChange(stamp, literal(until, xsd + "dateTimeStamp")) : null;
    if (stamp && !change) throw new Error("历史时间源只读，不能通过表单改写。");
    if (change) return [change];
    if (!["ontology", "vocabulary"].includes(end.sourceId)) throw new Error("历史时间源只读。");
    return [add(end.sourceId as VocabularyEditSource, end.triple.object.value, time + "inXSDDateTimeStamp", literal(until, xsd + "dateTimeStamp"))];
  }
  if (!["ontology", "vocabulary"].includes(claim.sourceId)) throw new Error("历史声明来源只读。");
  const source = claim.sourceId as VocabularyEditSource, point = `${claimIri}/closed-at`;
  fresh(snapshot, [point]);
  return [add(source, interval, time + "hasEnd", named(point)), add(source, point, rdfType, named(time + "Instant")),
    add(source, point, time + "inXSDDateTimeStamp", literal(until, xsd + "dateTimeStamp"))];
}
/** 事件发生时间引用与独立观察时间；空端点保留未知。 */
export interface EventInput { iri: string; timeIri: string; kind: "point" | "interval"; from: string; to: string; observed: string }

/** 事件编辑引用全新时间模板，旧时间资源原样保留；观察时间与事件发生时间分开。 */
export function eventChanges(snapshot: VocabularySnapshot, source: VocabularyEditSource, input: EventInput): VocabularyChange[] {
  const { iri, timeIri, kind, from, to, observed } = input;
  if (!absoluteIri(iri)) throw new Error("事件必须有明确绝对IRI。");
  if (observed && timestampTicks(observed) === null) throw new Error("观察时间必须有明确时区。");
  const temporalIris = [timeIri, ...(kind === "interval" && from ? [timeIri + "/from"] : []),
    ...(kind === "interval" && to ? [timeIri + "/to"] : [])];
  if (temporalIris.includes(iri)) throw new Error("事件与时间模板必须使用不同IRI。");
  fresh(snapshot, temporalIris);
  const old = only(snapshot, iri, time + "hasTime", true), observation = only(snapshot, iri, semantic + "observedAtUtc", true);
  const registered = snapshot.triples.some(row => row.triple.subject.kind === "iri" && row.triple.subject.value === iri
    && row.triple.predicate === rdfType && row.triple.object.value === semantic + "Event");
  if (!registered && snapshot.triples.some(row => row.triple.subject.value === iri)) throw new Error("此IRI已被其它资源使用。");
  const result = registered ? [] : [add(source, iri, rdfType, named(semantic + "Event"))];
  if (old) {
    const change = vocabularyChange(old, named(timeIri));
    if (!change) throw new Error("原事件时间字段只读。");
    result.push(change);
  } else result.push(add(source, iri, time + "hasTime", named(timeIri)));
  if (observation) {
    const change = vocabularyChange(observation, observed ? literal(observed, xsd + "dateTimeStamp") : null);
    if (!change) throw new Error("原观察时间字段只读。");
    result.push(change);
  } else if (observed) result.push(add(source, iri, semantic + "observedAtUtc", literal(observed, xsd + "dateTimeStamp")));
  return [...result, ...temporalChanges(source, timeIri, kind, from, kind === "interval" ? to : "")];
}
