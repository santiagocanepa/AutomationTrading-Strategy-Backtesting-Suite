import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Funciones para la lista de follow
// Funciones para la lista de nofollow
export function getusersFollowingAndGenderchek(): string[] {
  const jsonPath = path.resolve(__dirname, '../List/usersFollowingAndGenderchek.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return [];
  }
}

export function saveusersFollowingAndGenderchek(username: string): void {
  const jsonPath = path.resolve(__dirname, '../List/usersFollowingAndGenderchek.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    const usernames = JSON.parse(data);

    usernames.push(username);

    fs.writeFileSync(jsonPath, JSON.stringify(usernames, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error writing to JSON file at ${jsonPath}:`, error);
  }
}

// Funciones para la lista de solo follow
export function getUsernamesOnlyFollow(): Record<string, string[]> {
  const jsonPath = path.resolve(__dirname, '../List/usersOnlyFollowing.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return {};
  }
}

export function saveUsernameOnlyFollow(username: string): void {
  const jsonPath = path.resolve(__dirname, '../List/usersOnlyFollowing.json');
  const today = new Date().toLocaleDateString('es-ES'); // Formato DD/MM/AAAA

  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    const usernamesByDate = JSON.parse(data);

    if (!usernamesByDate[today]) {
      usernamesByDate[today] = [];
    }
    usernamesByDate[today].push(username);

    fs.writeFileSync(jsonPath, JSON.stringify(usernamesByDate, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error writing to JSON file at ${jsonPath}:`, error);
  }
}

// Funciones para la lista de unfollow
export function getusersFollowingChekAndFollowers(): string[] {
  const jsonPath = path.resolve(__dirname, '../List/usersFollowingChekAndFollowers.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return [];
  }
}

export function saveusersFollowingChekAndFollowers(username: string): void {
  const jsonPath = path.resolve(__dirname, '../List/usersFollowingChekAndFollowers.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    const usernames = JSON.parse(data);

    usernames.push(username);

    fs.writeFileSync(jsonPath, JSON.stringify(usernames, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error writing to JSON file at ${jsonPath}:`, error);
  }
}

// Funciones para el recuento diario
export function getDailyCounts(jsonPath: string): { [date: string]: number } {
  try {
    if (!fs.existsSync(jsonPath)) {
      return {};
    }
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return {};
  }
}

export function updateDailyCount(jsonPath: string): void {
  try {
    const counts = getDailyCounts(jsonPath);
    const today = new Date().toISOString().split('T')[0]; // Obtener la fecha en formato YYYY-MM-DD
    counts[today] = (counts[today] || 0) + 1;

    fs.writeFileSync(jsonPath, JSON.stringify(counts, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error updating JSON file at ${jsonPath}:`, error);
  }
}

// Verificar si se ha alcanzado el límite diario
export function checkDailyLimit(jsonPath: string, limit: number): boolean {
  const counts = getDailyCounts(jsonPath);
  const today = new Date().toISOString().split('T')[0]; // Obtener la fecha en formato YYYY-MM-DD
  return (counts[today] || 0) >= limit;
}

// Funciones para la lista de requests pendientes
export function getUsersRequestPendientes(): Record<string, string[]> {
  const jsonPath = path.resolve(__dirname, '../List/usersRequestPendientes.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return {};
  }
}

export function saveUserRequestPendiente(username: string): void {
  const jsonPath = path.resolve(__dirname, '../List/usersRequestPendientes.json');
  const today = new Date().toLocaleDateString('es-ES'); // Formato DD/MM/AAAA

  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    const requestsByDate = JSON.parse(data);

    if (!requestsByDate[today]) {
      requestsByDate[today] = [];
    }
    requestsByDate[today].push(username);

    fs.writeFileSync(jsonPath, JSON.stringify(requestsByDate, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error writing to JSON file at ${jsonPath}:`, error);
  }
}

// Funciones para la lista de usuarios dejados de seguir
export function getUserUnfollowed(): string[] {
  const jsonPath = path.resolve(__dirname, '../List/userUnfollowed.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error(`Error reading JSON file at ${jsonPath}:`, error);
    return [];
  }
}

export function saveUserUnfollowed(username: string): void {
  const jsonPath = path.resolve(__dirname, '../List/userUnfollowed.json');
  try {
    const data = fs.readFileSync(jsonPath, 'utf-8');
    const usernames = JSON.parse(data);

    usernames.push(username);

    fs.writeFileSync(jsonPath, JSON.stringify(usernames, null, 2), 'utf-8');
  } catch (error) {
    console.error(`Error writing to JSON file at ${jsonPath}:`, error);
  }
}
