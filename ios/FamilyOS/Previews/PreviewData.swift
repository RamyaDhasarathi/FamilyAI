// PREVIEW DATA. Plausible, slightly messy sample content for Xcode previews
// and design comparison only: a household of four, a school morning, a bill
// paid and one not, an errand half-way through. Decoded through the same
// JSON the server sends, so a preview and a live screen share one shape.
// Nothing here reaches a device build's screens.
import Foundation
import SwiftUI

enum PreviewData {
    static func decode<T: Decodable>(_ json: String) -> T {
        try! API.decoder.decode(T.self, from: Data(json.utf8))
    }

    static let today = Calendar.current.startOfDay(for: Date())
    static func day(_ offset: Int) -> String { API.dayOnly.string(from: Calendar.current.date(byAdding: .day, value: offset, to: today)!) }

    static let householdId = "11111111-1111-1111-1111-111111111111"
    static let amma = "22222222-2222-2222-2222-222222222222"
    static let appa = "33333333-3333-3333-3333-333333333333"
    static let varali = "44444444-4444-4444-4444-444444444444"
    static let sashreek = "55555555-5555-5555-5555-555555555555"

    static let members: [Member] = decode("""
    [
      {"id":"\(amma)","household_id":"\(householdId)","display_name":"Kanimozhi","role":"guardian","email":"kani@example.com","telegram_linked":true,"date_of_birth":"1986-03-14"},
      {"id":"\(appa)","household_id":"\(householdId)","display_name":"Arunmozhi","role":"guardian","email":"arun@example.com","telegram_linked":false,"date_of_birth":"1984-11-02"},
      {"id":"\(sashreek)","household_id":"\(householdId)","display_name":"Sashreek","role":"child","school":"Aachi Global School","class_label":"4-A","date_of_birth":"2017-06-21"},
      {"id":"\(varali)","household_id":"\(householdId)","display_name":"Varali","role":"child","school":"Aachi Global School","class_label":"KG-1","date_of_birth":"2021-09-09"}
    ]
    """)

    static let brief: Brief = decode("""
    {"date":"\(day(0))","display_name":"Arunmozhi","counts":{"due":3,"proposed":2},"more":0,"items":[
      {"reason":"due","rank":1,"title":"PTM for Grade 4, Room 12","why":"Parent-teacher meeting; bring the progress diary","when":"today","due_date":"\(day(0))","due_time":"09:00","action":"attend","status":"accepted","optional":false,"contested":false,"subject_name":"Sashreek","subject_member_id":"\(sashreek)","artifact_id":"aaaaaaaa-0000-0000-0000-000000000001"},
      {"reason":"due","rank":2,"title":"Pay Term 2 tuition fee","why":"₹48,000 to Aachi Global School, by Friday","when":"today","due_date":"\(day(0))","action":"pay","status":"accepted","optional":false,"contested":false,"pay_url":"https://example.com/pay","subject_name":"Varali","artifact_id":"aaaaaaaa-0000-0000-0000-000000000002"},
      {"reason":"proposed","rank":3,"title":"Science fair entries","why":"Entry form and a one-page abstract","when":"Thursday","due_date":"\(day(4))","action":"submit","status":"proposed","optional":false,"contested":false,"subject_name":"Sashreek","obligation_id":"bbbbbbbb-0000-0000-0000-000000000001","artifact_id":"aaaaaaaa-0000-0000-0000-000000000003"},
      {"reason":"proposed","rank":4,"title":"Diwali holidays, 20 to 24 Oct","why":"School closed; add to the family calendar?","when":"20 Oct","due_date":"\(day(11))","action":"note","status":"proposed","optional":true,"contested":false,"obligation_id":"bbbbbbbb-0000-0000-0000-000000000002","artifact_id":"aaaaaaaa-0000-0000-0000-000000000004"},
      {"reason":"clash","rank":5,"title":"Swimming class","why":"4:30 PM at the club","when":"today","due_date":"\(day(0))","due_time":"16:30","action":"attend","status":"accepted","optional":false,"contested":false,"clashes":["Dentist, Varali, 4:45 PM"],"subject_name":"Varali","artifact_id":"aaaaaaaa-0000-0000-0000-000000000005"},
      {"reason":"money","rank":6,"title":"Airtel is ₹480 above its usual","why":"₹1,940.98 this month against ₹1,460 most months","when":"this month","optional":true,"contested":false},
      {"reason":"due","rank":7,"title":"Renew Varali's passport","why":"Expires 12 Mar 2027; renewals take months","when":"in 9 weeks","due_date":"\(day(63))","action":"renew","status":"accepted","optional":false,"contested":false,"subject_name":"Varali","artifact_id":"aaaaaaaa-0000-0000-0000-000000000006"},
      {"reason":"handled","rank":8,"title":"Airtel Black bill","why":"paid — ₹1,940.98 receipt from Bharti Airtel on \(day(-1))","when":"yesterday","optional":true,"contested":false,"handled_by_name":"the receipt","artifact_id":"aaaaaaaa-0000-0000-0000-000000000007"}
    ]}
    """)

    static let events: [CalendarEvent] = decode("""
    [
      {"id":"cccccccc-0000-0000-0000-000000000001","summary":"Dentist, Varali","starts_at":"\(day(0))T16:45:00+05:30","ends_at":"\(day(0))T17:30:00+05:30","all_day":false},
      {"id":"cccccccc-0000-0000-0000-000000000002","summary":"Dinner at Priya's","starts_at":"\(day(1))T19:30:00+05:30","ends_at":"\(day(1))T22:00:00+05:30","all_day":false}
    ]
    """)

    static let errands: [Errand] = decode("""
    [
      {"id":"dddddddd-0000-0000-0000-000000000001","service":"urbancompany","kind":"booking","title":"AC service for two split units","status":"running","params_sha256":"9f2c7a1e4b3d5c6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f","created_by":"\(appa)","spec":{"what":"AC service, 2 split units","where":{"service":"urbancompany"},"limits":{"max_amount":3000,"currency":"INR"},"payment":{"mode":"pay_after_service"}}},
      {"id":"dddddddd-0000-0000-0000-000000000002","service":"myclassboard","kind":"look","title":"Read the school app's announcements","status":"done","params_sha256":"1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b","created_by":"\(appa)","spec":{"what":"Announcements","where":{"service":"myclassboard","label":"MyClassBoard school app","on":"the phone"}}}
    ]
    """)

    static let todos: [Todo] = decode("""
    [
      {"id":"eeeeeeee-0000-0000-0000-000000000001","title":"Buy a progress diary cover","due_date":"\(day(0))","assigned_to":"\(amma)"},
      {"id":"eeeeeeee-0000-0000-0000-000000000002","title":"Book the club's car park for Saturday","due_date":"\(day(2))","assigned_to":"\(appa)"}
    ]
    """)

    /// A session with the sample household signed in, for previews only.
    @MainActor static func session() -> Session {
        let s = Session()
        s.members = members
        return s
    }
}
