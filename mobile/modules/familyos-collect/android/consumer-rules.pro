# The collecting layer runs in the background on WorkManager (expo-background-task, services/collectTask.ts). WorkManager
# keeps its queue in a Room database whose code Room generates (WorkDatabase_Impl) and finds by name at start-up. The
# release build's shrinker (R8, android.enableMinifyInReleaseBuilds) renamed it, so the app crashed on launch
# ("Failed to create an instance of … WorkDatabase", 30 Oct 2026). Keep every Room database's generated class by name.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class androidx.work.impl.WorkDatabase_Impl { *; }
