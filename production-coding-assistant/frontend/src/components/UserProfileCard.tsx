import React from 'react';

interface UserProfileCardProps {
  user: {
    name: string;
    email: string;
    avatar: string;
  };
}

export const UserProfileCard: React.FC<UserProfileCardProps> = ({ user }) => {
  return (
    <div className="group relative w-full max-w-sm rounded-2xl bg-zinc-900/80 p-6 shadow-xl backdrop-blur-sm border border-zinc-800 transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:border-zinc-700">
      {/* Decorative background glow that appears on hover */}
      <div className="absolute inset-0 -z-10 rounded-2xl bg-gradient-to-br from-blue-500/10 via-transparent to-purple-500/10 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      
      <div className="flex flex-col items-center gap-4">
        {/* Avatar Container with Premium Ring Effect */}
        <div className="relative">
          <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-blue-500 to-purple-600 opacity-40 blur transition-all duration-300 group-hover:opacity-100 group-hover:blur-md" />
          <img
            src={user.avatar || 'https://i.pravatar.cc/150?img=68'}
            alt={`${user.name}'s avatar`}
            className="relative h-24 w-24 rounded-full object-cover border-2 border-zinc-900 shadow-inner bg-zinc-800"
          />
        </div>

        {/* User Info */}
        <div className="text-center">
          <h3 className="text-xl font-semibold tracking-tight text-zinc-100">{user.name}</h3>
          <p className="text-sm text-zinc-400 mt-0.5">{user.email}</p>
        </div>

        {/* Action Button */}
        <button
          type="button"
          className="mt-2 w-full rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-semibold text-zinc-900 shadow-sm transition-all duration-300 hover:bg-white hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-zinc-900"
        >
          Follow
        </button>
      </div>
    </div>
  );
};

// Example usage to show how it should look in the file:
// <UserProfileCard 
//   user={{ 
//     name: 'Alex Developer', 
//     email: 'alex@example.com', 
//     avatar: 'https://i.pravatar.cc/150?img=68' 
//   }} 
// />
