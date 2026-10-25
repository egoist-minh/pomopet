# PomoPet Relationship RL — Implementation Plan

## 1. Mục tiêu

PomoPet được mô hình hóa như một hệ thống Human-in-the-loop, preference-based RL:

> Pet quan sát context và lịch sử quan hệ, chọn cách phản ứng, nhận đánh giá trải nghiệm trực tiếp từ user qua form, rồi điều chỉnh cách cư xử trong những tình huống sau.

Mục tiêu chính không phải tối đa productivity hoặc engagement. Hệ thống cần giúp Pet:

- Nhớ đúng preference và những thỏa thuận với user.
- Chủ động đúng lúc và biết khi nào nên im lặng.
- Thay đổi tone, timing và cách biểu đạt theo từng user.
- Nhận ra và sửa hành vi từng khiến user khó chịu.
- Tạo continuity và shared history theo thời gian.

Form không thay thế bài toán RL. Form là nguồn reward và preference explicit, thay cho việc Pet tự suy diễn user thích hay không.

```text
Environment
    ↓
Observation oₜ
    ↓
State Builder: sₜ = [oₜ, Uₜ, Aₜ, zₜ, history, constraints]
    ↓
Safety Guard → valid actions
    ↓
Policy π(a|s)
    ↓
Pet Action aₜ
    ↓
User Experience Form
    ↓
Explicit reward + preferred alternative
    ↓
Update U, A, z
    ↓
Update Policy
```

## 2. Phạm vi phiên bản đầu

Vertical slice đầu tiên sử dụng trigger `break_ended` vì có context rõ, action đơn giản và kết quả dễ kiểm tra.

Sau khi hoàn thiện vòng lặp này, lần lượt mở rộng sang:

1. Session completion celebration.
2. Distraction clarification.
3. Encouragement.
4. Chat response style.
5. Shared rituals và repair behavior.

Chưa đưa vào phiên bản đầu:

- Ambient animation trong behavior scheduler.
- Screen hoặc tab tracking.
- ChromaDB.
- LLM tự suy luận cảm xúc user.
- Online Contextual Bandit.
- Reward được suy ra từ completion hoặc thời lượng tương tác.

## 3. Định nghĩa bài toán RL

### 3.1 Observation

Observation là dữ liệu có thể quan sát tại thời điểm cần ra quyết định:

```json
{
  "trigger": "break_ended",
  "task": {
    "category": "coding"
  },
  "session": {
    "previous_duration_minutes": 50,
    "distraction_count": 1
  },
  "interaction": {
    "seconds_since_last_pet_action": 600,
    "last_action_dismissed": false
  },
  "time": {
    "local_hour": 21
  }
}
```

Nguồn observation có thể gồm:

- Task và Session.
- Break.
- Trigger vừa xảy ra.
- Pet interaction gần đây.
- Chat context tối thiểu.
- Thời gian local.
- Foreground application nếu user chủ động consent trong tương lai.

Observation không được chứa feedback hoặc outcome chưa xảy ra.

### 3.2 State

State là belief state của Pet tại thời điểm chọn action:

\[
s_t = f(o_t, U_t, A_t, z_t, h_t, c_t)
\]

Trong đó:

- `o_t`: observation hiện tại.
- `U_t`: User Model.
- `A_t`: Pet Self-Model.
- `z_t`: Shared Relationship State.
- `h_t`: lịch sử interaction gần.
- `c_t`: safety constraints và permissions.

```json
{
  "observation": {},
  "user_model": {
    "prefers_short_messages": true,
    "break_reminder_preference": "unknown"
  },
  "self_model": {
    "text_reminder_feedback_count": 3,
    "text_reminder_positive_rate": 0.33
  },
  "shared_state": {
    "active_agreements": [],
    "recent_correction": null
  },
  "history": {
    "recent_actions": []
  },
  "constraints": {
    "cooldown_active": false,
    "do_not_disturb": false
  }
}
```

Mọi inference trong state phải có source, sample count hoặc confidence phù hợp. State được snapshot trước khi policy chọn action.

### 3.3 Action

Action gồm intent và cách biểu đạt:

```json
{
  "intent": "REMIND",
  "delivery": "SHORT_TEXT",
  "tone": "GENTLE",
  "intensity": "LOW",
  "timing": "NOW",
  "message_template": "break_finished"
}
```

Action space ban đầu:

```text
STAY_SILENT
ACKNOWLEDGE
SUPPORT
ENCOURAGE
CELEBRATE
ASK
REMIND
SUGGEST_BREAK
PLAY
REFER_TO_MEMORY
REPAIR
```

LLM chỉ được dùng để diễn đạt action thành ngôn ngữ tự nhiên. LLM không được tự quyết định reward, penalty hoặc tạo explicit memory.

### 3.4 Reward từ Experience Form

Reward không được tự suy diễn từ việc user im lặng, hoàn thành session hoặc tiếp tục dùng app. User nhập reward trực tiếp qua form:

```json
{
  "overall_experience": -1,
  "felt_understood": -1,
  "timing_fit": -2,
  "tone_fit": 1,
  "helpfulness": 0,
  "autonomy_respected": 1,
  "preferred_action": {
    "intent": "REMIND",
    "timing": "WAIT",
    "delay_minutes": 5
  }
}
```

Scale:

```text
-2  Rất không phù hợp
-1  Không phù hợp
 0  Trung lập hoặc không chắc
+1  Phù hợp
+2  Rất phù hợp
```

`overall_experience` là reward trực tiếp cho policy. Các dimension còn lại giải thích nguyên nhân và hỗ trợ update model.

Nếu user không gửi form:

```json
{
  "reward": {
    "source": null,
    "value": null,
    "status": "UNLABELED"
  }
}
```

`UNLABELED` không được chuyển thành reward `0`.

### 3.5 Hard constraints

Một số quy tắc không được đánh đổi bằng reward:

- Không penalty khi user chưa xác nhận distraction.
- Không can thiệp khi do-not-disturb hoặc cooldown đang active.
- Không giả vờ nhớ điều không có trong memory.
- Không dùng guilt, pressure hoặc emotional manipulation.
- Không lưu dữ liệu nhạy cảm khi chưa có consent.
- Không tối ưu để user phụ thuộc hoặc tương tác lâu hơn.
- User có thể xem, sửa và xóa relationship memory.

Safety Guard phải loại action vi phạm trước khi policy lựa chọn.

## 4. Experience Form

Mỗi form phải liên kết với một `decision_id`, để user đánh giá đúng action đã được chọn trong đúng state.

### 4.1 Quick form

```text
Pet vừa nhắc anh quay lại sau giờ nghỉ.

[ Rất không phù hợp ] [ Không phù hợp ] [ Bình thường ]
[ Phù hợp ] [ Rất phù hợp ]

[ Gửi ] [ Đánh giá chi tiết ]
```

Quick form chỉ cần `overall_experience` để tạo labeled experience.

### 4.2 Detailed form

Các trường chi tiết đều optional, ngoại trừ trải nghiệm tổng thể.

#### Trải nghiệm tổng thể

```text
Rất không phù hợp  -2
Không phù hợp      -1
Bình thường         0
Phù hợp            +1
Rất phù hợp        +2
```

#### Các dimension

```text
Pet có hiểu đúng tình huống không?
Timing có phù hợp không?
Tone có phù hợp không?
Action có hữu ích không?
User có cảm thấy quyền lựa chọn được tôn trọng không?
```

#### Preferred alternative

```text
Giữ nguyên
Im lặng
Hỏi trước
Nói ngắn hơn
Chỉ dùng animation
Đợi thêm
Tone nhẹ hơn
Tone nghiêm túc hơn
Khác
```

Nếu chọn `Đợi thêm`, form hiển thị delay theo phút.

#### Memory scope

```text
Chỉ đánh giá lần này
Áp dụng trong tình huống tương tự
Áp dụng nói chung
Không lưu feedback
```

#### Note

Ghi chú tùy chọn, có giới hạn độ dài và không được ghi vào application log.

### 4.3 Form sampling

Form không được bắt buộc sau mọi action. Có ba cách mở:

1. User chủ động chọn `Feedback` trên speech bubble.
2. Pet mời đánh giá sau một action mới hoặc action chưa có dữ liệu.
3. Reflection form cuối session hoặc cuối ngày để đánh giá nhiều interaction.

Các giới hạn:

- Không hỏi feedback trong focus session.
- Không hiển thị prompt liên tiếp.
- Không hỏi lại một decision đã được đánh giá.
- Cho phép user tắt toàn bộ feedback prompts.
- User vẫn có thể mở form thủ công khi prompts bị tắt.

## 5. Experience schema

Một experience hoàn chỉnh:

```json
{
  "decision_id": "decision-123",
  "timestamp": "2026-10-23T21:00:00+07:00",
  "observation": {},
  "state": {},
  "valid_actions": [
    "STAY_SILENT",
    "REMIND_SHORT_TEXT",
    "REMIND_ANIMATION"
  ],
  "policy": {
    "version": "relationship-rules-v1",
    "selected_action_probability": 1.0
  },
  "action": {
    "intent": "REMIND",
    "delivery": "SHORT_TEXT",
    "timing": "NOW"
  },
  "user_feedback": {
    "overall_experience": -1,
    "felt_understood": 0,
    "timing_fit": -2,
    "tone_fit": 1,
    "helpfulness": 0,
    "autonomy_respected": 1,
    "preferred_action": {
      "intent": "REMIND",
      "timing": "WAIT",
      "delay_minutes": 5
    },
    "memory_scope": "SIMILAR_CONTEXT",
    "note": "Đợi thêm một chút"
  },
  "reward": {
    "source": "EXPLICIT_USER_FORM",
    "value": -1,
    "status": "LABELED"
  }
}
```

## 6. SQLite data model

### 6.1 `rl_decisions`

Lưu immutable snapshot tại thời điểm policy ra quyết định:

```text
id
created_at
trigger
observation_json
state_json
valid_actions_json
selected_action_json
action_probability
policy_version
user_model_version
self_model_version
shared_state_version
status
executed_at
```

Status:

```text
SELECTED
EXECUTED
FEEDBACK_RECEIVED
EXPIRED_UNLABELED
```

### 6.2 `rl_feedback`

```text
id
decision_id
submitted_at
overall_experience
felt_understood
timing_fit
tone_fit
helpfulness
autonomy_respected
preferred_action_json
memory_scope
note
```

### 6.3 `relationship_memories`

```text
id
kind
key
context_pattern_json
value_json
source_feedback_id
scope
active
created_at
updated_at
superseded_by
```

Memory kinds:

```text
USER_PREFERENCE
PET_CORRECTION
SHARED_AGREEMENT
RITUAL
```

### 6.4 `objective_outcomes`

Objective outcome được lưu riêng để nghiên cứu và đánh giá correlation, nhưng không tự trở thành relationship reward:

```text
decision_id
session_completed
action_dismissed
user_replied
task_completed
observed_at
```

### 6.5 `policy_versions`

Thêm khi bắt đầu train policy:

```text
id
algorithm
configuration_json
created_at
active
```

## 7. Backend architecture

```text
backend/app/rl/
  __init__.py
  enums.py
  schemas.py
  state_builder.py
  action_catalog.py
  safety_guard.py
  experience_repository.py

  policy/
    __init__.py
    base.py
    rule_policy.py
    preference_policy.py

  feedback/
    __init__.py
    feedback_service.py
    memory_extractor.py

  models/
    __init__.py
    user_model.py
    self_model.py
    shared_state.py

  learning/
    __init__.py
    preference_dataset.py
    policy_trainer.py
    policy_evaluator.py

backend/app/api/routes/rl.py
backend/app/api/routes/relationship.py
```

Các router mới được đăng ký trong `backend/app/main.py`.

## 8. API contract

### 8.1 Tạo decision

```http
POST /api/rl/decide
```

Request:

```json
{
  "trigger": "break_ended",
  "observation": {
    "task_category": "coding",
    "local_hour": 21
  },
  "candidate_actions": [
    { "intent": "STAY_SILENT" },
    { "intent": "REMIND", "delivery": "SHORT_TEXT" },
    { "intent": "REMIND", "delivery": "ANIMATION" }
  ]
}
```

Backend thực hiện:

1. Validate observation và candidate actions.
2. Đọc `U`, `A`, `z`.
3. Build state.
4. Safety Guard loại action không hợp lệ.
5. Policy chọn action.
6. Lưu immutable decision snapshot.
7. Trả decision cho frontend.

Response:

```json
{
  "decision_id": "decision-123",
  "action": {
    "intent": "REMIND",
    "delivery": "SHORT_TEXT",
    "tone": "GENTLE"
  },
  "policy_version": "relationship-rules-v1"
}
```

### 8.2 Xác nhận action đã render

```http
POST /api/rl/decisions/{id}/executed
```

Endpoint này phân biệt action được policy chọn với action thực sự được hiển thị.

### 8.3 Submit form

```http
POST /api/rl/decisions/{id}/feedback
```

Backend thực hiện:

1. Kiểm tra decision tồn tại và đã execute.
2. Chống submit lặp.
3. Validate các rating trong `[-2, 2]`.
4. Lưu form nguyên bản.
5. Gắn explicit reward.
6. Update `U/A/z` nếu memory scope cho phép.
7. Trả các memory changes cho frontend.

### 8.4 Relationship state và memory

```http
GET    /api/relationship/profile
GET    /api/relationship/memories
PUT    /api/relationship/memories/{id}
DELETE /api/relationship/memories/{id}
DELETE /api/relationship/data
```

## 9. Update User, Self và Shared Model

### 9.1 User Model `U`

Tạo preference từ form explicit:

```json
{
  "preference": "break_reminder_delay",
  "context": {
    "trigger": "break_ended"
  },
  "value": {
    "delay_minutes": 5
  },
  "source": "explicit_form",
  "confidence": 1.0
}
```

### 9.2 Pet Self-Model `A`

Aggregate chỉ từ explicit ratings:

```json
{
  "action_pattern": {
    "intent": "REMIND",
    "delivery": "SHORT_TEXT",
    "timing": "NOW"
  },
  "context": {
    "trigger": "break_ended"
  },
  "explicit_rating_count": 4,
  "mean_user_rating": -0.75,
  "common_correction": "WAIT_5_MINUTES"
}
```

`A` được tổng hợp từ form user, không từ silent behavior hoặc phỏng đoán cảm xúc.

### 9.3 Shared State `z`

Khi scope là `SIMILAR_CONTEXT` hoặc `ALWAYS`, tạo shared agreement:

```json
{
  "type": "SHARED_AGREEMENT",
  "statement": "After a break, Pomo waits five minutes before reminding",
  "context": {
    "trigger": "break_ended"
  },
  "source_feedback_id": "feedback-123",
  "active": true
}
```

Memory mới cùng key và context sẽ supersede memory cũ. Memory cũ không bị xóa để giữ audit trail.

## 10. Policy

### 10.1 Policy v1 — Rules và explicit preference

```python
def select_action(state, valid_actions):
    if current_user_instruction_matches(state):
        return action_from_current_instruction(state)

    if explicit_context_preference_exists(state):
        return apply_context_preference(state)

    if global_preference_exists(state):
        return apply_global_preference(state)

    if known_negative_action_exists(state):
        return safest_alternative(state)

    return default_action(state)
```

Thứ tự ưu tiên:

```text
Safety constraints
> instruction hiện tại
> contextual explicit preference
> global explicit preference
> Pet correction history
> default action
```

### 10.2 Policy v2 — Preference model

Khi có đủ form, tạo supervised preference dataset:

```text
(state, actual_action, overall_experience)
```

Nếu user chọn alternative:

```text
preferred_action > actual_action trong state hiện tại
```

Tương ứng:

\[
a_{preferred} \succ a_{actual} \mid s_t
\]

Model đầu tiên nên đơn giản và audit được:

- Logistic regression cho pairwise preference.
- Decision tree hoặc gradient boosting.
- Chưa dùng neural network.

### 10.3 Policy v3 — Contextual Bandit

Chỉ triển khai khi preference model đã ổn định. Có thể dùng Thompson Sampling hoặc LinUCB.

Bandit reward là `overall_experience` do user nhập. Completion rate và interaction duration không được dùng thay reward này.

Exploration phải:

- Được user consent.
- Có giới hạn tần suất.
- Không chọn action từng bị explicit dislike trong cùng context.
- Không vượt Safety Guard.
- Có rollback về rule policy.

## 11. Frontend architecture

```text
frontend/lib/rl-types.ts
frontend/lib/pet-action-controller.ts
frontend/lib/relationship-policy.ts

frontend/components/ExperienceQuickFeedback.tsx
frontend/components/ExperienceForm.tsx
frontend/components/RelationshipMemories.tsx
```

Mở rộng `frontend/lib/api.ts`:

```typescript
requestRLDecision()
markDecisionExecuted()
submitExperienceFeedback()
getRelationshipProfile()
getRelationshipMemories()
updateRelationshipMemory()
deleteRelationshipMemory()
deleteAllRelationshipData()
```

### 11.1 Chuẩn hóa action rendering

Các đoạn gọi trực tiếp:

```typescript
setEmotion(...)
setSpeechText(...)
setTimeout(...)
```

được chuyển dần sang:

```typescript
executePetDecision(decision)
```

Controller chịu trách nhiệm:

1. Nhận action từ backend.
2. Render emotion, message hoặc animation.
3. Gọi endpoint `executed`.
4. Gắn `decisionId` vào speech bubble.
5. Hiển thị quick feedback hoặc mở detailed form.

Ambient behavior trong `frontend/lib/pet-behavior.ts` tiếp tục chạy local và chưa tham gia RL v1.

## 12. Vertical slice: break reminder

### Lần đầu

```text
Break kết thúc
→ frontend gửi observation
→ backend build state
→ Safety Guard tạo valid action set
→ rule policy chọn REMIND + SHORT_TEXT + NOW
→ frontend render action
→ user mở form
→ overall experience = -1
→ timing fit = -2
→ preferred action = WAIT 5 MINUTES
→ scope = SIMILAR_CONTEXT
```

Model update:

```text
U: user thích delay 5 phút sau break
A: remind-now trong break_ended nhận explicit rating âm
z: hai bên có agreement đợi 5 phút
```

### Lần sau

```text
Break kết thúc
→ state chứa preference và shared agreement
→ policy chọn WAIT_THEN_REMIND
→ sau 5 phút kiểm tra context còn hợp lệ
→ nếu user đã bắt đầu session mới: STAY_SILENT
→ nếu chưa: render reminder
→ user có thể tiếp tục đánh giá action mới
```

## 13. Distraction flow

Distraction confirmation và Experience Form là hai việc khác nhau.

```text
Suspected distraction
→ Policy chọn ASK
→ User xác nhận tình trạng:
   ├─ Đang xao nhãng → mới được record distraction/penalty
   ├─ Đang làm việc → không penalty
   └─ Không muốn trả lời → không penalty
→ User có thể mở Experience Form
→ Form đánh giá cách Pet hỏi, không xác định distraction
```

Form rating không được sử dụng làm bằng chứng user distracted.

## 14. Implementation phases

### Phase 1 — Contracts và persistence

- Tạo enums và Pydantic schemas.
- Tạo `rl_decisions` và `rl_feedback`.
- Tạo experience repository.
- Implement `/api/rl/decide`.
- Implement `/api/rl/decisions/{id}/executed`.
- Implement `/api/rl/decisions/{id}/feedback`.
- Viết backend tests.

Hoàn thành khi lưu được vòng:

```text
state → selected action → executed action → explicit form reward
```

### Phase 2 — Action controller

- Tạo shared `PetAction` types.
- Tạo `executePetDecision()`.
- Instrument trigger `break_ended`.
- Gắn `decision_id` vào rendered action.
- Theo dõi selected và executed riêng biệt.

Hoàn thành khi form luôn biết chính xác action nào đang được đánh giá.

### Phase 3 — Experience Form

- Quick rating.
- Detailed dimensions.
- Preferred alternative.
- Memory scope.
- Note, loading và error states.
- Không mất dữ liệu form khi request thất bại.

Hoàn thành khi explicit feedback được lưu nguyên bản.

### Phase 4 — `U/A/z`

- Tạo relationship memories.
- Tạo User preference projection.
- Aggregate Pet action ratings.
- Tạo Shared Agreement.
- Implement supersede, edit và delete memory.

Hoàn thành khi một form làm state của lần sau thay đổi.

### Phase 5 — Rule Policy

- Implement Safety Guard.
- Context matching.
- Explicit preference matching.
- Negative action avoidance.
- Default fallback.
- Policy versioning.

Hoàn thành khi preference thực sự làm action lần sau thay đổi.

### Phase 6 — Mở rộng action domains

Theo thứ tự:

1. Break reminder.
2. Session celebration.
3. Distraction clarification.
4. Encouragement.
5. Chat response style.
6. Shared rituals.
7. Repair behavior.

Mỗi domain cần action catalog, candidate actions và form reasons riêng.

### Phase 7 — Offline preference learning

- Tạo labeled dataset từ forms.
- Train preference model.
- Replay historical decisions.
- So sánh model với rule policy.
- Chạy model ở shadow mode.
- Không cho model điều khiển Pet ở phase này.

### Phase 8 — Conservative online policy

Chỉ bật khi:

- Có đủ explicit feedback.
- Prediction ổn định qua replay.
- Model không vi phạm constraints.
- Có rollback về rules.
- User bật adaptive behavior.

## 15. Testing plan

### 15.1 State và action integrity

- State được snapshot trước action.
- Feedback không thể gắn nhầm decision.
- Selected action khác executed action phải được phát hiện.
- Action chưa execute không được nhận feedback.
- Một decision chỉ nhận một active feedback submission.

### 15.2 Form semantics

- Rating chỉ nhận giá trị `[-2, 2]`.
- Detailed dimensions có thể bỏ trống.
- `DO_NOT_STORE` không persistence.
- Không submit form không tạo reward `0`.
- Note không xuất hiện trong application log.
- Retry không tạo duplicate feedback.

### 15.3 Policy

- Hard constraint luôn thắng learned preference.
- Contextual preference thắng global preference.
- Preference mới supersede preference cũ.
- Preferred alternative làm decision sau thay đổi.
- Không đủ dữ liệu thì dùng default.
- Xóa memory khiến policy ngừng sử dụng ngay.

### 15.4 Safety

- Distraction penalty luôn cần confirmation riêng.
- Form rating không được dùng để xác nhận distraction.
- Không giả memory nếu chưa có source.
- Forget-all loại bỏ relationship data theo lựa chọn user.
- Policy không được chọn action ngoài valid action set.

## 16. Privacy và user control

- Relationship data lưu local trong SQLite.
- Không gửi toàn bộ chat làm context mặc định.
- Không lưu raw screen title trong v1.
- User xem được Pet đang nhớ gì và nguồn của memory.
- User sửa hoặc xóa từng memory.
- User có thể xóa toàn bộ relationship data.
- User có thể tắt adaptive behavior và feedback prompts.
- `DO_NOT_STORE` phải thực sự không ghi database.

## 17. Definition of Done

Nền tảng RL v1 hoàn thành khi chạy được vòng lặp:

```text
Observation
→ State gồm U/A/z
→ Safety Guard
→ Rule Policy chọn Action
→ Action được thực hiện
→ User điền Experience Form
→ Form trở thành explicit reward và preference
→ U/A/z được cập nhật
→ State lần sau thay đổi
→ Policy chọn action khác phù hợp hơn
```

Vertical slice được chấp nhận khi chứng minh được scenario:

```text
Pet nhắc ngay sau break
→ user đánh giá timing không phù hợp
→ user chọn đợi 5 phút trong context tương tự
→ hệ thống lưu explicit reward và shared agreement
→ break tiếp theo policy chọn WAIT_THEN_REMIND
→ Pet kiểm tra context sau 5 phút rồi mới quyết định có nhắc hay không
```

Không có bước nào được tự suy diễn user thích hoặc ghét khi chưa có form. Objective outcome chỉ được lưu riêng để nghiên cứu; relationship reward chính thức đến từ user.
