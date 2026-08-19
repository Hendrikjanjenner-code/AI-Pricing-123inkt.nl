export * from "./generated/api";
export * from "./generated/types";
// Expliciete re-export lost de naamsbotsing op tussen het zod-object voor de
// path-parameters en het type voor de query-parameters van hetzelfde endpoint
// (orval genereert beide als "<OperationId>Params").
export {
  GetCompetitorScoreDetailParams,
  GetCompetitorFullProfileParams,
} from "./generated/api";
