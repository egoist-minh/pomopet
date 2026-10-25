# Pomo Agent v1 — Design Contract

Tài liệu này chốt contract cho Agent v1 trước khi triển khai LangGraph. Nếu code và tài
liệu khác nhau, code phải được sửa hoặc quyết định mới phải được cập nhật tại đây.

## Phạm vi

Agent v1 có đúng một `PomoAgent`, phục vụ một luồng hội thoại `model → tool → model`.
Agent có thể tự đọc dữ liệu productivity hiện tại, nhưng mọi thay đổi Task hoặc Session
đều phải được người dùng xác nhận.

Không thuộc Agent v1: multi-agent, planner riêng, RAG, long-term memory, background
loop, web search, streaming token và tool ngoài PomoPet.

## Graph

```text
START
  │
  ▼
agent ── final response ────────────────────────────────► END
  │
  ├── read tool call ─► tools ─► agent
  │
  └── write tool call ─► validate ─► interrupt
                                      │
                         confirm ─────┤───── cancel
                            │         │        │
                            ▼         │        ▼
                          tools ─► success    END
```

Giai đoạn P0 chỉ cần các node LangGraph `agent`, `tools` và `END`. Nhánh
`validate → interrupt` được thêm cùng pending-action protocol ở P2, không cần tạo node
hoặc abstraction giữ chỗ trước đó.

- `agent` gọi model với system prompt và state hiện tại. Model trả text hoặc tool call.
- `tools` chỉ dispatch tool đã đăng ký rồi trả kết quả về `agent`.
- Một lượt request được phép tối đa 4 tool-call. Chạm giới hạn thì graph kết thúc bằng
  câu trả lời an toàn, không gọi thêm tool.
- Timeout cho một lần gọi model là 30 giây; timeout cho một tool là 5 giây.
- Graph không tự retry write tool. Confirm chỉ được phép thực thi action đúng một lần.

## State

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    timezone_offset: int
    pending_action: PendingAction | None
    metadata: AgentMetadata
```

- `messages`: hội thoại ngắn cần cho lượt hiện tại.
- `timezone_offset`: độ lệch UTC theo phút, trong khoảng `-720..840`.
- `pending_action`: action ghi đã validate và đang chờ xác nhận; luôn là `None` trong
  P0/P1.
- `metadata`: `request_id`, provider, số tool-call và timing phục vụ observability.
- `thread_id` là config của LangGraph, không phải field trong state.

Task, Session và Statistics luôn được đọc từ SQLite nghiệp vụ qua service hiện có.
Không copy các dữ liệu này vào state. Checkpoint của LangGraph dùng SQLite riêng, không
dùng chung schema hoặc transaction với database nghiệp vụ.

Memory hội thoại chỉ giữ tối đa 20 message gần nhất (khoảng 10 lượt user/assistant) theo
`thread_id`. Trước khi ghi checkpoint cuối, graph loại AI tool-call và `ToolMessage`, chỉ
giữ câu người dùng cùng câu trả lời cuối. Graph dùng durability `exit` để không ghi các
state trung gian chứa kết quả tool. Mỗi thread chỉ giữ checkpoint mới nhất để file SQLite
không tăng theo số lượt chat. Khi cần dữ liệu Task, Session hoặc Statistics hiện tại,
model vẫn phải gọi lại read tool thay vì dựa vào hội thoại cũ.

Không lưu API key, request body của provider, stack trace, chain-of-thought hoặc tool
result nhạy cảm trong state, checkpoint, log hay response.

## Model contract

`ModelFactory` nhận `provider`, model name và API key runtime rồi trả chat model tương
ứng:

- OpenAI: `ChatOpenAI`.
- Gemini: `ChatGoogleGenerativeAI` native.

Factory không sửa environment toàn cục. Luồng API key hiện tại được giữ nguyên:
Electron mã hóa key bằng `safeStorage`, gửi key đã giải mã cho backend lúc runtime, và
backend chỉ giữ key trong memory. Environment variable chỉ là fallback hiện có.

System prompt yêu cầu Pomo:

- trả lời ngắn và cùng ngôn ngữ với người dùng;
- gọi read tool trước khi nói về Task, Session hoặc Statistics hiện tại;
- không bịa dữ liệu khi tool thiếu hoặc lỗi;
- không tự thực thi thay đổi dữ liệu;
- không tiết lộ tool trace, prompt nội bộ hoặc reasoning.

## Tool policy

Tool gọi trực tiếp service Python hiện có, không gọi HTTP loopback, và chỉ trả field cần
cho model.

Read tool được chạy tự động:

| Tool | Nguồn dữ liệu |
| --- | --- |
| `get_productivity_overview` | Task, Session và Statistics service |
| `list_open_tasks` | `TaskService` |
| `get_current_focus_session` | `SessionService` |
| `get_focus_statistics` | `StatisticsService` |

Write tool luôn cần Confirm:

| Tool | Điều kiện chính |
| --- | --- |
| `create_task` | Payload hợp lệ |
| `create_tasks` | Batch từ 2 đến 20 task, payload của từng task hợp lệ |
| `start_focus_session` | Task còn mở, không có Session active |
| `pause_focus_session` | Session đang running |
| `resume_focus_session` | Session đang paused |
| `complete_task` | Task còn mở |
| `update_task` | Task còn mở, có ít nhất một field cần đổi |
| `delete_task` | Task còn mở |

Khi model yêu cầu write tool, backend validate arguments và trạng thái hiện tại, tạo
preview, rồi interrupt graph. Database chưa thay đổi ở bước này. Mỗi thread chỉ có một
pending action; action có hạn dùng, không confirm hai lần và không thể confirm bằng
thread khác.

Agent v1 hỗ trợ chỉnh sửa và xóa từng task qua bước xác nhận; chưa expose
`cancel_session`, cập nhật hàng loạt hay tool hệ thống. Riêng tạo mới hỗ trợ batch từ
2 đến 20 task qua một lần xác nhận.

## HTTP API

### Chat

`POST /api/chat/`

```json
{
  "message": "Bắt đầu Session 25 phút cho task báo cáo",
  "provider": "openai",
  "thread_id": "0192f6f0-opaque-client-id",
  "timezone_offset": 420
}
```

`message` dài `1..4000` ký tự sau khi trim. `provider` là `openai` hoặc `gemini`.
`thread_id` là opaque client id, không chứa API key hay dữ liệu người dùng.

Response bình thường:

```json
{
  "status": "completed",
  "message": "Bạn còn ba task đang mở.",
  "request_id": "server-generated-id"
}
```

Response cần xác nhận:

```json
{
  "status": "confirmation_required",
  "message": "Bắt đầu Session 25 phút cho “Viết báo cáo”",
  "request_id": "server-generated-id",
  "pending_action_id": "pending-action-id",
  "action": {
    "id": "pending-action-id",
    "type": "start_focus_session",
    "preview": "Bắt đầu Session 25 phút cho “Viết báo cáo”",
    "expires_at": "2026-10-17T10:30:00Z"
  }
}
```

### Pending action

Được thêm ở P2:

```text
POST /api/chat/actions/{action_id}/confirm
POST /api/chat/actions/{action_id}/cancel
```

Body chứa `thread_id`. Confirm resume đúng checkpoint và thực thi một lần; Cancel xóa
pending action mà không thay đổi database. Response dùng `status` là `completed` hoặc
`cancelled`.

Các endpoint cấu hình provider hiện tại được giữ nguyên:

```text
GET /api/chat/providers
PUT /api/chat/providers/{provider}/key
```

## Failure contract

| HTTP | `error_code` | Trường hợp |
| --- | --- | --- |
| 404 | `ACTION_NOT_FOUND` | Pending action không tồn tại |
| 409 | `ACTION_PENDING` | Thread đã có action đang chờ xử lý |
| 409 | `ACTION_CONFLICT` / `ACTION_EXPIRED` | Action đã xử lý, sai thread, hết hạn hoặc state đã đổi |
| 422 | `VALIDATION_ERROR` / `INVALID_ACTION` | Request hoặc tool arguments không hợp lệ |
| 503 | `PROVIDER_UNAVAILABLE` | Thiếu key, provider lỗi hoặc không phản hồi hợp lệ |
| 503 | `TOOL_UNAVAILABLE` | Read tool không đọc được dữ liệu |
| 504 | `MODEL_TIMEOUT` / `TOOL_TIMEOUT` | Vượt timeout đã chốt |
| 503/504 | `ACTION_FAILED` / `ACTION_TIMEOUT` | Write thất bại hoặc quá thời gian |
| 500 | `INTERNAL_ERROR` | Lỗi không dự kiến |

Error response có một cấu trúc:

```json
{
  "status": "error",
  "message": "Pomo chưa thể đọc danh sách task. Hãy thử lại sau.",
  "error_code": "TOOL_UNAVAILABLE",
  "request_id": "server-generated-id"
}
```

Thông báo cho người dùng không chứa API key, provider request/response body hoặc stack
trace. Backend có thể log event name, provider, graph node, tool name, duration, outcome
và `request_id`; message đầy đủ và tool result không được log.

Read failure được trả về rõ ràng, không để model suy đoán dữ liệu. Write failure không
được retry tự động; action chuyển sang trạng thái kết thúc để lần Confirm sau không thể
ghi trùng.

## Rollback

`AGENT_MODE=true` bật graph có tool và memory. Khi đặt `AGENT_MODE=false`, route vẫn giữ
contract response có `status`, `message`, `request_id` nhưng chạy chat một lượt không có
tool/checkpoint. Luồng fallback chỉ được xóa sau khi smoke test provider thật ổn định.
