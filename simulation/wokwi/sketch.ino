// Brodeuse CNC Singer -- test de cablage sous Wokwi
//
// Ce croquis N'EST PAS le firmware final (ce sera FluidNC).
// Il sert uniquement a verifier, en simulation, que les GPIO sont bien
// cables : il fait tourner les trois axes et lit les quatre capteurs.
//
// Le brochage reprend exactement firmware/fluidnc-config.yaml.
//
// CHOIX DES PINS D'ENTREE
// On utilise ici des GPIO qui possedent un PULL-UP INTERNE (4, 21, 22, 32),
// active par INPUT_PULLUP. Plus aucune resistance externe n'est necessaire :
// c'est plus simple, et deterministe en simulation.
//
// (La premiere version utilisait 34/35/36/39, en entree seule et SANS pull-up
//  interne : ces pins flottent et donnent des lectures fantomes. A retenir
//  pour la vraie carte -- voir README.)

// ---- Sorties vers les drivers ----
const int X_STEP = 26, X_DIR = 16;
const int Y_STEP = 25, Y_DIR = 27;
const int Z_STEP = 17, Z_DIR = 14;
const int ENABLE = 13;   // partage par les trois drivers (actif a l'etat bas)

// ---- Entrees capteurs (pull-up interne) ----
const int SW_X = 4;      // fin de course X
const int SW_Y = 21;     // fin de course Y
const int HALL = 22;     // index Z (point mort haut de l'aiguille)
const int THREAD = 32;   // detecteur de casse-fil

void pulse(int stepPin, int n, int us) {
  for (int i = 0; i < n; i++) {
    digitalWrite(stepPin, HIGH);
    delayMicroseconds(us);
    digitalWrite(stepPin, LOW);
    delayMicroseconds(us);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(X_STEP, OUTPUT); pinMode(X_DIR, OUTPUT);
  pinMode(Y_STEP, OUTPUT); pinMode(Y_DIR, OUTPUT);
  pinMode(Z_STEP, OUTPUT); pinMode(Z_DIR, OUTPUT);
  pinMode(ENABLE, OUTPUT);

  // Pull-up interne active : au repos la broche lit 1, appuye elle lit 0.
  pinMode(SW_X, INPUT_PULLUP);
  pinMode(SW_Y, INPUT_PULLUP);
  pinMode(HALL, INPUT_PULLUP);
  pinMode(THREAD, INPUT_PULLUP);

  digitalWrite(ENABLE, LOW);   // drivers actifs
  Serial.println("=== Brodeuse CNC Singer -- test de cablage ===");
  Serial.println("Appuie sur les boutons pour simuler les capteurs.");
}

void loop() {
  // Un "point" : le cadre bouge (X puis Y), puis l'aiguille pique (Z).
  digitalWrite(X_DIR, HIGH); pulse(X_STEP, 200, 800);
  digitalWrite(Y_DIR, HIGH); pulse(Y_STEP, 200, 800);
  digitalWrite(Z_DIR, HIGH); pulse(Z_STEP, 400, 400);   // Z = 1 tour = 1 point

  // Lecture des capteurs (0 = appuye, car tirage vers 3V3 au repos).
  Serial.print("Fin X:");   Serial.print(digitalRead(SW_X));
  Serial.print("  Fin Y:"); Serial.print(digitalRead(SW_Y));
  Serial.print("  Hall:");  Serial.print(digitalRead(HALL));
  Serial.print("  Fil:");   Serial.println(digitalRead(THREAD));

  if (digitalRead(THREAD) == LOW)
    Serial.println("  >> CASSE-FIL detecte -- la machine devrait s'arreter");
  if (digitalRead(HALL) == LOW)
    Serial.println("  >> Index Z -- aiguille au point mort haut");

  delay(500);
}
