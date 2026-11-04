#r "/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform/backend/tests/OntologyPlatform.AgentTests/bin/Debug/net10.0/Npgsql.dll"
open System
open System.IO
open System.Diagnostics
open System.Text
open System.Text.Json
open Npgsql
let password = File.ReadAllText("/Users/chasen/.codex/worktrees/g4-m1-main-integration-001/ontology-platform/.tools/security/g4-m1-main-integration-001-b-continue-20261104-20/platform-password").Trim()
let builder = NpgsqlConnectionStringBuilder()
builder.Host <- "127.0.0.1"
builder.Port <- 15432
builder.Database <- "platform"
builder.Username <- "platform"
builder.Password <- password
builder.Pooling <- false
use conn = new NpgsqlConnection(builder.ConnectionString)
conn.Open()
let measure label sql payload =
    use cmd = new NpgsqlCommand(sql, conn)
    cmd.CommandTimeout <- 5
    cmd.Parameters.AddWithValue("p",payload) |> ignore
    let query () = cmd.ExecuteScalar() |> ignore
    for i in 1..5 do query()
    let values = [|for i in 1..30 do let watch=Stopwatch.StartNew() in query(); yield watch.Elapsed.TotalMilliseconds|] |> Array.sort
    printfn "%s" (JsonSerializer.Serialize({|name=label; samples=30; inputBytes=Encoding.UTF8.GetByteCount(payload); minMs=values[0]; medianMs=values[15]; p95Ms=values[28]; totalMs=Array.sum values|}))
measure "small-in-small-out" "SELECT octet_length(@p::text)" "x"
measure "12KiB-in-small-out" "SELECT octet_length(@p::text)" (String.replicate 4096 "中")
measure "24KiB-in-small-out" "SELECT octet_length(@p::text)" (String.replicate 24576 "x")
measure "small-in-12KiB-out" "SELECT repeat(chr(20013),4096) WHERE @p::text='x'" "x"
